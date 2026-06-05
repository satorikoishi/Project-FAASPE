import numpy as np
import time

class KayakLoop:
    def __init__(self, xloop_factor=40000, rloop_factor=4000, slo=0.0):
        """
        Initialize the LoopAdjuster with given factors and the SLO (Service Level Objective).

        :param xloop_factor: Factor for X-loop adjustment (int)
        :param rloop_factor: Factor for R-loop adjustment (int)
        :param slo: Service Level Objective (SLO), target latency (float)
        """
        self.xloop_factor = xloop_factor
        self.rloop_factor = rloop_factor
        self.slo = slo

        # Internal state variables
        self.xloop_last_rdtsc = time.perf_counter()
        self.xloop_last_recvd = 0
        self.xloop_last_rate = 0
        self.xloop_last_X = 0
        self.ext_p = 50.0  # Starting value for ext_p

        self.rloop_last_rdtsc = time.perf_counter()
        self.rloop_last_recvd = 0
        self.kth = 0.0  # Placeholder for kth percentile value
        self.max_out = 16.0  # Initial max output threshold
        self.rloop_last_kth = 0.0
        
        self.latencies = []
    
    def update_latencies(self, new_latency):
        """
        Adds a new latency value and calculates the 98th percentile (kth) every 10th value
        after having more than 100 latencies in the list.
        
        :param new_latency: New latency value to be added (float)
        """
        # Add the new latency to the list
        self.latencies.append(new_latency)

        # Perform the 98th percentile calculation every time we have more than 100 latencies
        if len(self.latencies) > 100 and len(self.latencies) % 10 == 0:
            # Get the last 100 latencies
            recent_latencies = self.latencies[-100:]

            # Calculate the 98th percentile (kth)
            self.kth = np.percentile(recent_latencies, 98)

            print(f"Calculated 98th percentile (kth): {self.kth}")

    def update_rloop(self, recvd):
        """
        Update the R-loop based on received data and latency measurements.

        :param recvd: Number of requests received (int)
        :param latencies: List of latency measurements (list of floats)
        :return: Adjusted max output (float)
        """
        current_time = time.perf_counter()
        # If R-loop factor is set and we have enough latency data, perform the adjustment
        if self.rloop_factor != 0 and current_time - self.rloop_last_rdtsc > 1 / self.rloop_factor and len(self.latencies) > 100 and len(self.latencies) % self.rloop_factor == 0:
            
            # Compute the rate of the loop
            rloop_rate = 100 * (recvd - self.rloop_last_recvd) / (current_time - self.rloop_last_rdtsc)
            self.rloop_last_rdtsc = current_time
            self.rloop_last_recvd = recvd

            # Compute the offset based on SLO and kth percentile
            lat_offset = self.slo - self.kth
            out_delta = 3e-6 * lat_offset  # Adjustment based on latency offset

            # Update max_out with AIMD-like behavior
            if self.max_out + out_delta > 2.0:
                self.max_out += out_delta
            else:
                self.max_out = max(2.0, self.max_out * 0.5)

        return self.max_out

    def update_xloop(self, recvd):
        """
        Update the X-loop based on the received data.

        :param recvd: Number of requests received (int)
        :return: Adjusted ext_p (float)
        """
        current_time = time.perf_counter()
        if self.xloop_factor != 0 and current_time - self.xloop_last_rdtsc > 1 / self.xloop_factor and len(self.latencies) > 100 and len(self.latencies) % self.xloop_factor == 0:

            # Calculate the time difference between loop iterations
            xloop_rate = 100 * (recvd - self.xloop_last_recvd) / (current_time - self.xloop_last_rdtsc)
            self.xloop_last_rdtsc = current_time
            self.xloop_last_recvd = recvd

            # Compute the rate change and the gradient for ext_p adjustment
            delta_rate = xloop_rate - self.xloop_last_rate
            self.xloop_last_rate = xloop_rate

            delta_X = self.ext_p - self.xloop_last_X
            self.xloop_last_X = self.ext_p

            grad = 2.0 * delta_rate / delta_X if delta_X != 0 else 0

            # Apply bounded gradient adjustment to ext_p
            bounded_offset_X = -1.0
            if grad > 0:
                if grad < 1.0:
                    bounded_offset_X = 1.0
                elif grad > 20.0:
                    bounded_offset_X = 5.0
                else:
                    bounded_offset_X = grad
            else:
                if grad > -1.0:
                    bounded_offset_X = -1.0
                elif grad < -20.0:
                    bounded_offset_X = -5.0
                else:
                    bounded_offset_X = grad

            # Update ext_p based on the bounded offset
            new_X = self.ext_p + bounded_offset_X
            if 0 <= new_X <= 100:
                self.ext_p = new_X
            else:
                self.ext_p -= bounded_offset_X  # Bounce back if out of bounds

        return self.ext_p

if __name__ == "__main__":
    # Initialize LoopAdjuster with default factors
    adjuster = KayakLoop(slo=2.0)

    # Simulate some received packets and latency values
    recvd_packets = 500
    latencies = [0.5] * 200  # Simulated latency values
    
    adjuster.update_latencies(latencies)

    # Update the loops and get the adjusted parameters
    adjusted_max_out = adjuster.update_rloop(recvd=recvd_packets)
    adjusted_ext_p = adjuster.update_xloop(recvd=recvd_packets)

    print(f"Adjusted max_out: {adjusted_max_out}")
    print(f"Adjusted ext_p: {adjusted_ext_p}")

    # Change SLO and update again
    adjusted_ext_p_new = adjuster.update_xloop(recvd=recvd_packets)
    print(f"Adjusted ext_p after SLO change: {adjusted_ext_p_new}")