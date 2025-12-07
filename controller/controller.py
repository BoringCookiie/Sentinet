from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ether_types
from ryu.lib import hub
import operator
import os

class SentinetController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(SentinetController, self).__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.datapaths = {} # Store connected switches
        self.monitor_thread = hub.spawn(self._monitor)

    # Event 1: Switch connects to Controller (Handshake)
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # Install the "Table-Miss" flow entry.
        # "If you don't know what to do with a packet, send it to Controller"
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)
        print(f"*** Switch {datapath.id} Connected")

    # Event 2: A Packet comes in (The Loop)
    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        
        # Get the ID of the switch (s1, s2, etc.)
        dpid = datapath.id
        self.mac_to_port.setdefault(dpid, {})

        # Analyze the packet
        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        
        # Ignore IPv6 (LLDP) noise for clarity
        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        if eth.ethertype == 0x86dd: # 0x86dd is IPv6
            return

        dst = eth.dst
        src = eth.src
        print(f"IN: dpid={datapath.id} src={src} dst={dst}")
        in_port = msg.match['in_port']

        # LOGIC: Learn where the Source is
        # "Oh, MAC X is connected to Port Y"
        self.mac_to_port[dpid][src] = in_port

        # LOGIC: Decide output port
        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
        else:
            # We don't know where destination is yet -> Flood to all ports
            out_port = ofproto.OFPP_FLOOD

        actions = [parser.OFPActionOutput(out_port)]

        # If we know the output port, install a flow to skip Controller next time
        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst, eth_src=src)
            self.add_flow(datapath, 1, match, actions)

        # Send the packet out
        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data
        out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                  in_port=in_port, actions=actions, data=data)
        datapath.send_msg(out)

    def add_flow(self, datapath, priority, match, actions, buffer_id=None):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(datapath=datapath, priority=priority,
                                match=match, instructions=inst)
        datapath.send_msg(mod)
    
    # EVENT: Store the switch object when it connects
    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, CONFIG_DISPATCHER])
    def _state_change_handler(self, ev):
        datapath = ev.datapath
        if ev.state == MAIN_DISPATCHER:
            if datapath.id not in self.datapaths:
                self.datapaths[datapath.id] = datapath
        elif ev.state == 'DEAD':
            if datapath.id in self.datapaths:
                del self.datapaths[datapath.id]

    # THREAD: Loop forever and ask for stats
    def _monitor(self):
        while True:
            for dp in self.datapaths.values():
                self._request_stats(dp)
            hub.sleep(2) # Wait 2 seconds

    def _request_stats(self, datapath):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        req = parser.OFPFlowStatsRequest(datapath)
        datapath.send_msg(req)

    # EVENT: Receive the stats (The "Input" for AI)
    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def _flow_stats_reply_handler(self, ev):
        body = ev.msg.body
        dpid = ev.msg.datapath.id
        
        # Filter to only host traffic flows (priority 1)
        host_flows = [flow for flow in body if flow.priority == 1]
        
        # Sort by packet count (Descending) for console display
        sorted_flows = sorted(host_flows, key=lambda flow: flow.packet_count, reverse=True)
        
        # 1. CONSOLE OUTPUT - For debugging
        print(f"\n--- Stats for Switch {dpid} ---")
        for stat in sorted_flows:
            print(f"Flow: {stat.match['eth_src']} -> {stat.match['eth_dst']} | "
                  f"Packets: {stat.packet_count} | Bytes: {stat.byte_count}")
        
        # 2. CSV LOGGING - For AI Training (with computed features)
        file_exists = os.path.isfile("traffic_data.csv")
        with open("traffic_data.csv", "a") as f:
            if not file_exists:
                f.write("timestamp,dpid,src,dst,packet_count,byte_count,"
                        "duration_sec,pps,bps,avg_pkt_size\n")
            
            for stat in host_flows:
                # Compute flow duration (seconds + nanoseconds)
                duration = stat.duration_sec + (stat.duration_nsec / 1e9)
                
                # Compute derived features (avoid division by zero)
                if duration > 0:
                    pps = stat.packet_count / duration  # Packets Per Second
                    bps = stat.byte_count / duration    # Bytes Per Second
                else:
                    pps = 0
                    bps = 0
                
                if stat.packet_count > 0:
                    avg_pkt_size = stat.byte_count / stat.packet_count
                else:
                    avg_pkt_size = 0
                
                f.write(f"{ev.timestamp},{dpid},{stat.match['eth_src']},"
                        f"{stat.match['eth_dst']},{stat.packet_count},{stat.byte_count},"
                        f"{duration:.4f},{pps:.2f},{bps:.2f},{avg_pkt_size:.2f}\n")