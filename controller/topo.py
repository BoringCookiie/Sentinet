from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import RemoteController, OVSKernelSwitch
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel

class SentinetTopo(Topo):
    """
    Sentinet Network Topology
    =========================
    
                         [s1] (Core Switch)
                        / |  \\
                      /   |    \\
                    s2   s4     s5
                   /|     |      |\\
                 s3 h4   h5     h6 h7
                /|\\              |
              h1 h2 h3          h8
                   (attacker)
    
    Path Examples:
    - h1 → h7: s3 → s2 → s1 → s5 (4 hops)
    - h1 → h4: s3 → s2 (2 hops)  
    - h5 → h6: s4 → s1 → s5 (3 hops)
    
    This provides varied path lengths for Q-Learning without loops.
    
    ⚠️  CRITICAL SYNCHRONIZATION WARNING ⚠️
    ========================================
    The order of hosts and links here MUST EXACTLY MATCH the TOPOLOGY 
    constant in config.py. The Controller uses config.py to calculate 
    port numbers. If you add/remove/reorder ANY links or hosts here:
    
    1. Update TOPOLOGY['hosts'] in config.py to match host order
    2. Update TOPOLOGY['links'] in config.py to match link order
    
    Failure to sync will cause packets to route to WRONG PORTS!
    """
    def build(self):
        # ============================================
        # 1. Create Switches (5 switches - tree structure)
        # ============================================
        s1 = self.addSwitch('s1', cls=OVSKernelSwitch, protocols='OpenFlow13')  # Core
        s2 = self.addSwitch('s2', cls=OVSKernelSwitch, protocols='OpenFlow13')  # Distribution
        s3 = self.addSwitch('s3', cls=OVSKernelSwitch, protocols='OpenFlow13')  # Access (Left)
        s4 = self.addSwitch('s4', cls=OVSKernelSwitch, protocols='OpenFlow13')  # Access (Center)
        s5 = self.addSwitch('s5', cls=OVSKernelSwitch, protocols='OpenFlow13')  # Access (Right)

        # ============================================
        # 2. Create Hosts (8 hosts across the network)
        # ============================================
        # Left Branch (via s3) - User workstations
        h1 = self.addHost('h1', mac="00:00:00:00:00:01", ip="10.0.0.1/24")
        h2 = self.addHost('h2', mac="00:00:00:00:00:02", ip="10.0.0.2/24")
        h3 = self.addHost('h3', mac="00:00:00:00:00:03", ip="10.0.0.3/24")  # Attacker
        
        # Center Branch (via s2, s4) - Department servers
        h4 = self.addHost('h4', mac="00:00:00:00:00:04", ip="10.0.0.4/24")
        h5 = self.addHost('h5', mac="00:00:00:00:00:05", ip="10.0.0.5/24")
        
        # Right Branch (via s5) - Data center
        h6 = self.addHost('h6', mac="00:00:00:00:00:06", ip="10.0.0.6/24")
        h7 = self.addHost('h7', mac="00:00:00:00:00:07", ip="10.0.0.7/24")
        h8 = self.addHost('h8', mac="00:00:00:00:00:08", ip="10.0.0.8/24")

        # ============================================
        # 3. Create Links - BACKBONE (Switch to Switch)
        # ============================================
        # Core to Distribution/Access (High bandwidth backbone)
        self.addLink(s1, s2, bw=100, delay='1ms')   # Core ↔ Distribution
        self.addLink(s1, s4, bw=50,  delay='2ms')   # Core ↔ Access Center
        self.addLink(s1, s5, bw=100, delay='1ms')   # Core ↔ Access Right
        
        # Distribution to Access (Lower tier)
        self.addLink(s2, s3, bw=50,  delay='3ms')   # Distribution ↔ Access Left

        # ============================================
        # 4. Create Links - HOST CONNECTIONS
        # ============================================
        # Left branch hosts (s3)
        self.addLink(h1, s3, bw=100, delay='0.5ms')
        self.addLink(h2, s3, bw=100, delay='0.5ms')
        self.addLink(h3, s3, bw=100, delay='0.5ms')  # Attacker on edge
        
        # Center hosts (s2, s4)
        self.addLink(h4, s2, bw=100, delay='0.5ms')  # Directly on distribution
        self.addLink(h5, s4, bw=100, delay='0.5ms')
        
        # Right branch hosts (s5) - "Data Center"
        self.addLink(h6, s5, bw=1000, delay='0.1ms')  # Gigabit server
        self.addLink(h7, s5, bw=1000, delay='0.1ms')  # Gigabit server
        self.addLink(h8, s5, bw=100,  delay='0.5ms')  # Regular host

def run():
    setLogLevel('info')
    topo = SentinetTopo()
    
    # We use RemoteController because Ryu is running externally
    net = Mininet(topo=topo, 
                  controller=RemoteController, 
                  link=TCLink,
                  autoSetMacs=True)
    
    net.start()
    print("*** Network is UP. Running CLI...")
    CLI(net) # Opens the Mininet command prompt
    net.stop()

if __name__ == '__main__':
    run()