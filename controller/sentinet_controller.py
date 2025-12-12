"""
Sentinet Controller
===================
Main SDN Controller for the Sentinet Self-Healing Network.

Features:
- OpenFlow 1.3 L2 Learning Switch
- Real-time flow statistics collection
- AI integration (Sentinel for DDoS, Navigator for routing)
- Backend WebSocket communication
- Attack detection and mitigation

Usage:
    ryu-manager sentinet_controller.py
"""

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, DEAD_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ether_types, ipv4, arp
from ryu.lib import hub

import time
import os
import logging

# Local imports
from config import (
    POLL_INTERVAL, ALERT_COOLDOWN, TOPOLOGY,
    VERBOSE_STATS, CSV_LOGGING, CSV_FILE_PATH,
    BACKEND_ENABLED, SENTINEL_ENABLED, NAVIGATOR_ENABLED
)
from ai_interface import SentinelAI, NavigatorAI, format_flow_for_ai, prepare_navigator_input
from backend_client import BackendClient, MockBackendClient


class SentinetController(app_manager.RyuApp):
    """
    Sentinet SDN Controller
    
    The "Brain" of the self-healing network.
    Manages switches, detects attacks, and optimizes routing.
    """
    
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(SentinetController, self).__init__(*args, **kwargs)
        
        # =================================================================
        # Core Data Structures
        # =================================================================
        self.mac_to_port = {}      # {dpid: {mac: port}}
        self.datapaths = {}        # {dpid: datapath} - connected switches
        self.flow_stats = {}       # {dpid: [flow_stats]} - latest stats per switch
        self.prev_stats = {}       # {(dpid, src, dst): (packets, bytes, time)} - for delta calculation
        
        # =================================================================
        # AI Models
        # =================================================================
        self.sentinel = SentinelAI()
        self.navigator = NavigatorAI()
        
        # Initialize Navigator with topology (for Q-Learning routing)
        if NAVIGATOR_ENABLED:
            self.navigator.initialize_topology(TOPOLOGY)
        
        self.logger.info(f"[AI] Sentinel: {self.sentinel.get_status()}")
        self.logger.info(f"[AI] Navigator: {self.navigator.get_status()}")
        
        # =================================================================
        # Backend Connection
        # =================================================================
        if BACKEND_ENABLED:
            self.backend = BackendClient()
        else:
            self.backend = MockBackendClient()
        
        # =================================================================
        # Attack Tracking
        # =================================================================
        self.active_alerts = {}    # {(src, dst): expiry_timestamp}
        self.blocked_flows = set() # Set of (src, dst) tuples currently blocked
        
        # =================================================================
        # Start Background Threads  
        # =================================================================
        self.monitor_thread = hub.spawn(self._monitor_loop)
        self.logger.info("[SENTINET] Controller initialized")

    # =========================================================================
    # SWITCH CONNECTION HANDLERS
    # =========================================================================
    
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        """Handle switch connection and install table-miss flow."""
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        dpid = datapath.id
        
        # Install table-miss flow: send unknown packets to controller
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        self._add_flow(datapath, 0, match, actions)
        
        self.logger.info(f"[SWITCH] s{dpid} connected")
        
        # Notify backend of switch connection
        self.backend.send_switch_event("connected", dpid)
    
    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, CONFIG_DISPATCHER, DEAD_DISPATCHER])
    def state_change_handler(self, ev):
        """Track switch connect/disconnect."""
        datapath = ev.datapath
        dpid = datapath.id
        
        if ev.state == MAIN_DISPATCHER:
            if dpid not in self.datapaths:
                self.datapaths[dpid] = datapath
                self.logger.info(f"[SWITCH] s{dpid} registered")
                
                # Send topology to backend when first switch connects
                if len(self.datapaths) == 1:
                    self._send_topology()
                    # Re-initialize Navigator with topology (in case it failed earlier)
                    if NAVIGATOR_ENABLED and not self.navigator.brain:
                        self.navigator.initialize_topology(TOPOLOGY)
                    
        elif ev.state == DEAD_DISPATCHER:
            if dpid in self.datapaths:
                del self.datapaths[dpid]
                self.logger.info(f"[SWITCH] s{dpid} disconnected")
                self.backend.send_switch_event("disconnected", dpid)

    # =========================================================================
    # PACKET HANDLING (L2 Learning Switch)
    # =========================================================================
    
    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        """Handle incoming packets - L2 learning switch logic."""
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        
        dpid = datapath.id
        in_port = msg.match['in_port']
        
        # Parse packet
        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        
        # Ignore LLDP and IPv6
        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return
        if eth.ethertype == 0x86dd:  # IPv6
            return
        
        src_mac = eth.src
        dst_mac = eth.dst
        
        # Initialize MAC table for this switch
        self.mac_to_port.setdefault(dpid, {})
        
        # Learn source MAC
        self.mac_to_port[dpid][src_mac] = in_port
        
        # Check if this flow is blocked
        if self._is_blocked(src_mac, dst_mac):
            self.logger.warning(f"[BLOCK] Dropping packet from blocked flow: {src_mac} -> {dst_mac}")
            return
        
        # Determine output port
        if dst_mac in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst_mac]
        else:
            # Unknown destination - use Navigator AI or flood
            out_port = self._get_output_port(dpid, src_mac, dst_mac, ofproto)
        
        actions = [parser.OFPActionOutput(out_port)]
        
        # Install flow if we know the destination
        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst_mac, eth_src=src_mac)
            
            # Use short idle timeout for Navigator-routed flows (adaptive routing)
            # This forces re-evaluation of path when traffic patterns change
            if NAVIGATOR_ENABLED:
                self._add_flow(datapath, 1, match, actions, idle_timeout=5)
            else:
                self._add_flow(datapath, 1, match, actions)
        
        # Send packet out
        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data
            
        out = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=data
        )
        datapath.send_msg(out)

    def _get_output_port(self, dpid, src_mac, dst_mac, ofproto):
        """
        Get output port for a packet. Uses Navigator AI if available.
        
        Called by: packet_in_handler
        
        Logic:
        1. Ask Navigator AI for path (list of switch IDs)
        2. Find current switch position in path
        3. Determine next hop switch
        4. Look up port connecting to next hop
        """
        if NAVIGATOR_ENABLED:
            # Ask Navigator AI for optimal path
            graph = self.get_network_graph()
            path = self.navigator.get_path(src_mac, dst_mac, graph)
            
            if path:
                out_port = self._path_to_port(dpid, path, dst_mac)
                if out_port is not None:
                    self.logger.debug(f"[NAVIGATOR] Path {path}, using port {out_port}")
                    return out_port
        
        # Fallback: flood to all ports
        return ofproto.OFPP_FLOOD
    
    def _path_to_port(self, dpid: int, path: list, dst_mac: str) -> int:
        """
        Convert a path from Navigator AI to an output port.
        
        Args:
            dpid: Current switch datapath ID
            path: List of switch IDs from Navigator, e.g., ["s3", "s2", "s1", "s5"]
            dst_mac: Destination MAC address
            
        Returns:
            Output port number, or None if cannot determine
        """
        current_switch = f"s{dpid}"
        
        # Find current switch in path
        if current_switch not in path:
            return None
        
        current_idx = path.index(current_switch)
        
        # If we're at the last switch in path, the host is directly connected
        if current_idx == len(path) - 1:
            # Look up which port the destination host is on
            if dpid in self.mac_to_port and dst_mac in self.mac_to_port[dpid]:
                return self.mac_to_port[dpid][dst_mac]
            return None
        
        # Otherwise, find port to next hop switch
        next_switch = path[current_idx + 1]
        return self._get_port_to_switch(dpid, next_switch)
    
    def _get_port_to_switch(self, from_dpid: int, to_switch_id: str) -> int:
        """
        Get the port on from_dpid that connects to to_switch_id.
        
        Uses topology link information and learned port mappings.
        
        Args:
            from_dpid: Current switch datapath ID (e.g., 1 for s1)
            to_switch_id: Target switch ID (e.g., "s2")
            
        Returns:
            Port number, or None if not found
        """
        from_switch = f"s{from_dpid}"
        
        # Search in switch_ports mapping (built from topology)
        if not hasattr(self, '_switch_ports'):
            self._build_switch_port_map()
        
        key = (from_switch, to_switch_id)
        if key in self._switch_ports:
            return self._switch_ports[key]
        
        return None
    
    def _build_switch_port_map(self):
        """
        Build mapping of (switch, neighbor_switch) -> port.
        
        This is derived from the topology and port learning.
        Port numbers are assigned in order of link creation in topo.py.
        """
        self._switch_ports = {}
        
        # Build from topology links
        # In Mininet, ports are assigned incrementally as links are added
        # We need to track port assignments per switch
        switch_port_counter = {}
        
        for switch in TOPOLOGY['switches']:
            switch_port_counter[switch['id']] = 1  # Ports start at 1
        
        # First, host connections (these come first in topo.py)
        for host in TOPOLOGY['hosts']:
            switch_id = host['switch']
            # Host gets a port on its switch
            switch_port_counter[switch_id] += 1
        
        # Then, switch-to-switch links
        for link in TOPOLOGY['links']:
            from_sw = link['from']
            to_sw = link['to']
            
            # Port on from_switch connecting to to_switch
            from_port = switch_port_counter[from_sw]
            switch_port_counter[from_sw] += 1
            
            # Port on to_switch connecting to from_switch
            to_port = switch_port_counter[to_sw]
            switch_port_counter[to_sw] += 1
            
            self._switch_ports[(from_sw, to_sw)] = from_port
            self._switch_ports[(to_sw, from_sw)] = to_port
        
        self.logger.info(f"[NAVIGATOR] Switch port map built: {self._switch_ports}")
    
    def _get_host_switch(self, mac: str) -> str:
        """
        Get the switch ID that a host is connected to.
        
        Args:
            mac: Host MAC address
            
        Returns:
            Switch ID (e.g., "s3") or None
        """
        host = self.get_host_by_mac(mac)
        if host:
            return host['switch']
        return None

    # =========================================================================
    # FLOW MANAGEMENT
    # =========================================================================
    
    def _add_flow(self, datapath, priority, match, actions, idle_timeout=0, hard_timeout=0):
        """Install a flow rule on a switch."""
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(
            datapath=datapath,
            priority=priority,
            match=match,
            instructions=inst,
            idle_timeout=idle_timeout,
            hard_timeout=hard_timeout
        )
        datapath.send_msg(mod)
    
    def _block_flow(self, src_mac: str, dst_mac: str, duration: int = 60):
        """
        Block traffic between two hosts.
        
        Called by: Security AI when attack detected
        """
        self.logger.warning(f"[BLOCK] Blocking flow: {src_mac} -> {dst_mac} for {duration}s")
        
        # Add to blocked set
        self.blocked_flows.add((src_mac, dst_mac))
        
        # Install DROP rule on all switches
        for dpid, datapath in self.datapaths.items():
            parser = datapath.ofproto_parser
            match = parser.OFPMatch(eth_src=src_mac, eth_dst=dst_mac)
            actions = []  # Empty actions = DROP
            
            self._add_flow(datapath, priority=100, match=match, actions=actions,
                          hard_timeout=duration)
        
        # Schedule unblock
        hub.spawn_after(duration, self._unblock_flow, src_mac, dst_mac)
    
    def _unblock_flow(self, src_mac: str, dst_mac: str):
        """Remove block on a flow after timeout."""
        self.blocked_flows.discard((src_mac, dst_mac))
        self.logger.info(f"[UNBLOCK] Flow unblocked: {src_mac} -> {dst_mac}")
    
    def _is_blocked(self, src_mac: str, dst_mac: str) -> bool:
        """Check if a flow is currently blocked."""
        return (src_mac, dst_mac) in self.blocked_flows

    # =========================================================================
    # MONITORING & STATISTICS
    # =========================================================================
    
    def _monitor_loop(self):
        """Background thread: Poll switches for stats every POLL_INTERVAL seconds."""
        # Connect to backend
        self.backend.connect()
        
        while True:
            # Clean expired alerts
            self._clean_expired_alerts()
            
            # Request stats from all switches
            for dpid, dp in self.datapaths.items():
                self._request_stats(dp)
            
            hub.sleep(POLL_INTERVAL)
    
    def _request_stats(self, datapath):
        """Send flow stats request to a switch."""
        parser = datapath.ofproto_parser
        req = parser.OFPFlowStatsRequest(datapath)
        datapath.send_msg(req)
    
    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def flow_stats_reply_handler(self, ev):
        """Handle flow statistics from switches."""
        body = ev.msg.body
        dpid = ev.msg.datapath.id
        timestamp = ev.timestamp
        
        # Filter to priority 1 flows (host traffic, not table-miss)
        host_flows = [flow for flow in body if flow.priority == 1]
        
        # Format flows for processing
        # Format flows for processing
        formatted_flows = []
        for stat in host_flows:
            flow_data = format_flow_for_ai(stat, dpid, timestamp)
            
            # --- FIX: Calculate Instant PPS (Delta) instead of Lifetime Average ---
            
            # Key to identify the unique flow
            src = stat.match['eth_src']
            dst = stat.match['eth_dst']
            key = (dpid, src, dst)
            
            current_packets = stat.packet_count
            current_bytes = stat.byte_count
            current_time = timestamp
            
            pps = 0.0
            bps = 0.0
            
            if key in self.prev_stats:
                prev_packets, prev_bytes, prev_time = self.prev_stats[key]
                
                delta_packets = current_packets - prev_packets
                delta_bytes = current_bytes - prev_bytes
                delta_time = current_time - prev_time
                
                if delta_time > 0:
                    pps = delta_packets / delta_time
                    bps = (delta_bytes * 8) / delta_time
                    
                    # Ensure non-negative (counters might vary if switch sends out-of-order stats, though unlikely in single thread)
                    pps = max(0.0, pps)
                    bps = max(0.0, bps)
            
            # Update history
            self.prev_stats[key] = (current_packets, current_bytes, current_time)
            
            # Override the "Lifetime" stats from format_flow_for_ai
            flow_data['pps'] = pps
            flow_data['bps'] = bps
            
            # -------------------------------------------------------------
            
            formatted_flows.append(flow_data)
            
            # Run through Sentinel AI
            self._check_for_attack(flow_data)
        
        # Store latest stats
        self.flow_stats[dpid] = formatted_flows
        
        # Send to backend
        self._send_stats_to_backend(dpid, formatted_flows)
        
        # Update Navigator AI with link utilization (for Q-Learning)
        if NAVIGATOR_ENABLED:
            link_stats = self._calculate_link_utilization()
            self.navigator.update_link_stats(link_stats)
        
        # Log to CSV if enabled
        if CSV_LOGGING:
            self._log_to_csv(formatted_flows)
        
        # Console output if verbose
        if VERBOSE_STATS and formatted_flows:
            self._print_stats(dpid, formatted_flows)

    # =========================================================================
    # AI INTEGRATION
    # =========================================================================
    
    def _check_for_attack(self, flow_data: dict):
        """
        Run flow through Sentinel AI to detect attacks.
        
        Called by: flow_stats_reply_handler for each flow
        """
        src_mac = flow_data['src_mac']
        dst_mac = flow_data['dst_mac']
        pps = flow_data['pps']
        bps = flow_data['bps']
        avg_pkt_size = flow_data['avg_pkt_size']
        
        # Skip if already blocked
        if self._is_blocked(src_mac, dst_mac):
            return
        
        # Run prediction
        prediction_result = self.sentinel.predict(pps, bps, avg_pkt_size)
        
        # Handle Dictionary vs Boolean return
        is_attack = False
        attack_type = "Unknown"
        confidence = 0.0

        if isinstance(prediction_result, dict):
            is_attack = prediction_result.get('is_threat', False)
            attack_type = prediction_result.get('attack_type', "DDoS")
            confidence = prediction_result.get('confidence', 0.0)
        else:
            is_attack = bool(prediction_result)
        
        if is_attack:
            # Add the type to flow_data so the handler can print it
            flow_data['attack_type'] = attack_type 
            self._handle_attack_detected(flow_data)
    
    def _handle_attack_detected(self, flow_data: dict):
        """
        Handle detected attack: block flow and send alert.
        
        Called by: _check_for_attack when Sentinel detects anomaly
        """
        src_mac = flow_data['src_mac']
        dst_mac = flow_data['dst_mac']
        
        # Check alert cooldown (avoid duplicate alerts)
        alert_key = (src_mac, dst_mac)
        if alert_key in self.active_alerts:
            if time.time() < self.active_alerts[alert_key]:
                return  # Still in cooldown
        
        # Set alert cooldown
        self.active_alerts[alert_key] = time.time() + ALERT_COOLDOWN
        
        self.logger.error(f"[ATTACK] {flow_data.get('attack_type', 'DDoS')} detected: {src_mac} -> {dst_mac}")
        self.logger.error(f"[ATTACK] Stats: PPS={flow_data['pps']:.2f}, BPS={flow_data['bps']:.2f}")
        
        # Block the flow
        self._block_flow(src_mac, dst_mac, duration=60)
        
        # Send alert to backend
        alert = {
            "attacker_mac": src_mac,
            "target_mac": dst_mac,
            "pps": flow_data['pps'],
            "bps": flow_data['bps'],
            "action_taken": "BLOCKED",
            "block_duration_sec": 60
        }
        self.backend.send_alert(alert)
    
    def _clean_expired_alerts(self):
        """Remove expired alerts from tracking."""
        now = time.time()
        expired = [k for k, v in self.active_alerts.items() if v < now]
        for k in expired:
            del self.active_alerts[k]

    # =========================================================================
    # BACKEND COMMUNICATION
    # =========================================================================
    
    def _send_topology(self):
        """Send network topology to backend."""
        self.backend.send_topology(TOPOLOGY)
        self.logger.info("[BACKEND] Topology sent")
    
    def _send_stats_to_backend(self, dpid: int, flows: list):
        """Send flow statistics to backend."""
        stats = {
            "dpid": dpid,
            "flows": flows
        }
        self.backend.send_stats(stats)

    # =========================================================================
    # CSV LOGGING (for training data)
    # =========================================================================
    
    def _log_to_csv(self, flows: list):
        """Log flow statistics to CSV file."""
        file_exists = os.path.isfile(CSV_FILE_PATH)
        
        with open(CSV_FILE_PATH, "a") as f:
            if not file_exists:
                f.write("timestamp,dpid,src,dst,packet_count,byte_count,"
                       "duration_sec,pps,bps,avg_pkt_size\n")
            
            for flow in flows:
                f.write(f"{flow['timestamp']},{flow['dpid']},{flow['src_mac']},"
                       f"{flow['dst_mac']},{flow['packet_count']},{flow['byte_count']},"
                       f"{flow['duration_sec']:.4f},{flow['pps']:.2f},"
                       f"{flow['bps']:.2f},{flow['avg_pkt_size']:.2f}\n")

    # =========================================================================
    # CONSOLE OUTPUT
    # =========================================================================
    
    def _print_stats(self, dpid: int, flows: list):
        """Print flow statistics to console."""
        print(f"\n--- Stats for Switch s{dpid} ---")
        sorted_flows = sorted(flows, key=lambda f: f['pps'], reverse=True)
        
        for flow in sorted_flows[:5]:  # Top 5 flows
            status = "🔴 BLOCKED" if self._is_blocked(flow['src_mac'], flow['dst_mac']) else ""
            print(f"  {flow['src_mac']} -> {flow['dst_mac']} | "
                  f"PPS: {flow['pps']:.1f} | BPS: {flow['bps']:.1f} {status}")

    # =========================================================================
    # PUBLIC API - For AI Models to Call
    # =========================================================================
    
    def get_network_graph(self) -> dict:
        """
        Get current network graph for Navigator AI.
        
        Returns:
            Dictionary with:
            - adjacency: {switch_id: [{node, weight, utilization_bps}]}
            - link_stats: {(from, to): total_bps}
        
        The Navigator AI uses this to find optimal paths considering congestion.
        """
        graph = prepare_navigator_input(self.mac_to_port, TOPOLOGY)
        
        # Calculate link utilization from flow stats
        link_stats = self._calculate_link_utilization()
        
        # Add utilization to graph edges
        for switch_id, neighbors in graph.items():
            for neighbor in neighbors:
                link_key = (switch_id, neighbor['node'])
                reverse_key = (neighbor['node'], switch_id)
                
                # Get BPS for this link (sum of both directions)
                bps = link_stats.get(link_key, 0) + link_stats.get(reverse_key, 0)
                neighbor['utilization_bps'] = bps
                
                # Calculate congestion score (higher = more congested)
                # Use link bandwidth from topology
                bandwidth = neighbor.get('bw_mbps', 100) * 1_000_000  # Convert to bps
                if bandwidth > 0:
                    neighbor['congestion'] = min(1.0, bps / bandwidth)
                else:
                    neighbor['congestion'] = 0
        
        graph['_link_stats'] = link_stats
        return graph
    
    def _calculate_link_utilization(self) -> dict:
        """
        Calculate total bandwidth usage per link based on flow statistics.
        
        Returns:
            Dictionary: {(from_switch, to_switch): total_bps}
        
        Logic:
        - For each flow on each switch, determine which link it uses
        - Sum up BPS for flows traversing each link
        """
        link_usage = {}
        
        # Build switch port map if not exists
        if not hasattr(self, '_switch_ports'):
            self._build_switch_port_map()
        
        # Build reverse map: port -> neighbor_switch
        port_to_neighbor = {}
        for (from_sw, to_sw), port in self._switch_ports.items():
            dpid = int(from_sw[1:])  # "s1" -> 1
            port_to_neighbor[(dpid, port)] = to_sw
        
        # Analyze flows on each switch
        for dpid, flows in self.flow_stats.items():
            switch_id = f"s{dpid}"
            
            for flow in flows:
                out_port = flow.get('out_port', 0)
                bps = flow.get('bps', 0)
                
                # Determine which link this flow uses
                neighbor = port_to_neighbor.get((dpid, out_port))
                if neighbor:
                    link_key = (switch_id, neighbor)
                    link_usage[link_key] = link_usage.get(link_key, 0) + bps
        
        return link_usage
    
    def get_link_stats(self) -> list:
        """
        Get current link utilization statistics for monitoring/debugging.
        
        Returns:
            List of link stats with utilization info
        """
        link_stats = self._calculate_link_utilization()
        result = []
        
        for link in TOPOLOGY['links']:
            from_sw = link['from']
            to_sw = link['to']
            bandwidth = link.get('bw_mbps', 100) * 1_000_000
            
            # Get usage in both directions
            usage_fwd = link_stats.get((from_sw, to_sw), 0)
            usage_rev = link_stats.get((to_sw, from_sw), 0)
            total_usage = usage_fwd + usage_rev
            
            result.append({
                'from': from_sw,
                'to': to_sw,
                'bandwidth_bps': bandwidth,
                'usage_bps': total_usage,
                'utilization_pct': (total_usage / bandwidth * 100) if bandwidth > 0 else 0
            })
        
        return result
    
    def get_flow_features(self, src_mac: str = None, dst_mac: str = None) -> list:
        """
        Get flow features for Sentinel AI.
        
        Args:
            src_mac: Filter by source (optional)
            dst_mac: Filter by destination (optional)
            
        Returns:
            List of flow feature dictionaries
        """
        all_flows = []
        for dpid, flows in self.flow_stats.items():
            for flow in flows:
                if src_mac and flow['src_mac'] != src_mac:
                    continue
                if dst_mac and flow['dst_mac'] != dst_mac:
                    continue
                all_flows.append(flow)
        
        return all_flows
    
    def get_host_by_mac(self, mac: str) -> dict:
        """
        Get host information by MAC address.
        
        Returns:
            Host dict from topology or None
        """
        for host in TOPOLOGY['hosts']:
            if host['mac'] == mac:
                return host
        return None
    
    def get_active_alerts(self) -> list:
        """Get list of currently active security alerts."""
        now = time.time()
        return [
            {"src": k[0], "dst": k[1], "expires_in": v - now}
            for k, v in self.active_alerts.items()
            if v > now
        ]
