"""
Sentinet Diamond Topology (topo_smart.py)
=========================================
A multi-path topology designed to test Q-Learning based routing.

Structure:
    
         [h1]                          [h2]
           \                            /
            [s1] ========== Path A (FAST) ========== [s4]
              \                                   /
               \    Path B (SLOW/CONGESTED)      /
                \                               /
                 [s2] -------- [s3] ----------
                   (Limited BW)    (Limited BW)

Path Options from s1 to s4:
- Path A: s1 -> s4 (direct, high bandwidth - 100 Mbps)
- Path B: s1 -> s2 -> s3 -> s4 (longer, low bandwidth - 10 Mbps)

The AI should learn to prefer Path A, but fall back to Path B
if Path A becomes congested.

Usage:
    sudo python3 topo_smart.py
"""

from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import RemoteController, OVSKernelSwitch
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel


class DiamondTopo(Topo):
    """
    Diamond Topology for Multi-Path Q-Learning Testing
    
              h1
               |
              s1 (Start)
             /   \\
           /      \\
         s2        s4 (End) --- h2
          |         |
         s3 -------/
    
    Path A (Fast):   s1 -> s4         (100 Mbps, 1ms delay)
    Path B (Slow):   s1 -> s2 -> s3 -> s4  (10 Mbps, 10ms delay each hop)
    
    This forces the Q-Learning agent to:
    1. Learn that Path A is optimal under normal conditions
    2. Detect when Path A is congested
    3. Dynamically switch to Path B when necessary
    """
    
    def build(self):
        # ============================================
        # 1. Create Switches (Diamond Structure)
        # ============================================
        s1 = self.addSwitch('s1', cls=OVSKernelSwitch, protocols='OpenFlow13')  # Entry point
        s2 = self.addSwitch('s2', cls=OVSKernelSwitch, protocols='OpenFlow13')  # Slow path hop 1
        s3 = self.addSwitch('s3', cls=OVSKernelSwitch, protocols='OpenFlow13')  # Slow path hop 2  
        s4 = self.addSwitch('s4', cls=OVSKernelSwitch, protocols='OpenFlow13')  # Exit point
        
        # ============================================
        # 2. Create Hosts
        # ============================================
        h1 = self.addHost('h1', mac="00:00:00:00:00:01", ip="10.0.0.1/24")  # Source host
        h2 = self.addHost('h2', mac="00:00:00:00:00:02", ip="10.0.0.2/24")  # Destination host
        
        # ============================================
        # 3. Connect Hosts to Edge Switches
        # ============================================
        self.addLink(h1, s1, bw=100, delay='0.5ms')  # h1 connected to entry
        self.addLink(h2, s4, bw=100, delay='0.5ms')  # h2 connected to exit
        
        # ============================================
        # 4. PATH A: The Fast Path (Direct)
        # ============================================
        # High bandwidth, low latency - the "ideal" route
        self.addLink(s1, s4, bw=100, delay='1ms')  # 100 Mbps, 1ms
        
        # ============================================
        # 5. PATH B: The Slow Path (Multi-hop)
        # ============================================
        # Low bandwidth, high latency - the "backup" route
        self.addLink(s1, s2, bw=10, delay='10ms')  # 10 Mbps, 10ms (congested simulation)
        self.addLink(s2, s3, bw=10, delay='10ms')  # 10 Mbps, 10ms
        self.addLink(s3, s4, bw=10, delay='10ms')  # 10 Mbps, 10ms


# =============================================================================
# TOPOLOGY METADATA (for config.py sync)
# =============================================================================
# When using this topology, update config.py TOPOLOGY constant to:
DIAMOND_TOPOLOGY = {
    "switches": [
        {"id": "s1", "dpid": 1, "role": "entry"},
        {"id": "s2", "dpid": 2, "role": "slow_path"},
        {"id": "s3", "dpid": 3, "role": "slow_path"},
        {"id": "s4", "dpid": 4, "role": "exit"}
    ],
    "hosts": [
        {"id": "h1", "mac": "00:00:00:00:00:01", "ip": "10.0.0.1", "switch": "s1"},
        {"id": "h2", "mac": "00:00:00:00:00:02", "ip": "10.0.0.2", "switch": "s4"}
    ],
    "links": [
        # Host links (ports assigned first)
        {"from": "h1", "to": "s1", "bw_mbps": 100, "delay_ms": 0.5},
        {"from": "h2", "to": "s4", "bw_mbps": 100, "delay_ms": 0.5},
        # Path A - Fast
        {"from": "s1", "to": "s4", "bw_mbps": 100, "delay_ms": 1},
        # Path B - Slow  
        {"from": "s1", "to": "s2", "bw_mbps": 10, "delay_ms": 10},
        {"from": "s2", "to": "s3", "bw_mbps": 10, "delay_ms": 10},
        {"from": "s3", "to": "s4", "bw_mbps": 10, "delay_ms": 10}
    ]
}


def run():
    """Start the Diamond topology network."""
    setLogLevel('info')
    topo = DiamondTopo()
    
    print("\n" + "="*60)
    print("SENTINET DIAMOND TOPOLOGY - Q-Learning Test Environment")
    print("="*60)
    print("""
    Topology Structure:
    
         [h1 - Attacker/Source]
              |
             s1 (Entry)
            /   \\
          /      \\ (Fast Path - 100Mbps)
        s2        \\
         |         s4 (Exit) --- [h2 - Target]
        s3        /
          \\      /
           \\----/ (Slow Path - 10Mbps each)
    
    Test Commands:
    - h1 ping h2         : Test connectivity
    - h1 ping -i 0.1 h2  : Fast ping (stress test)
    - iperf h1 h2        : Bandwidth test
    """)
    print("="*60 + "\n")
    
    # Create network with RemoteController (Ryu)
    net = Mininet(
        topo=topo,
        controller=RemoteController,
        link=TCLink,
        autoSetMacs=True
    )
    
    net.start()
    print("*** Network is UP. Ryu controller should be running on port 6653.")
    print("*** Use 'pingall' to verify connectivity.")
    print("*** Type 'exit' or Ctrl+D to stop.\n")
    
    CLI(net)
    net.stop()


if __name__ == '__main__':
    run()
