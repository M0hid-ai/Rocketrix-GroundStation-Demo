"""LoRa downlink model: time-on-air, radio duty, path loss, packet loss, corruption, latency."""

from __future__ import annotations

import math
import random
from collections import deque
from dataclasses import dataclass

from .config import LinkConfig


def lora_airtime_s(payload_bytes: int, sf: int, bw_khz: float, cr: int,
                   preamble: int = 8, explicit_header: bool = True, crc: bool = True) -> float:
    """Semtech SX127x time-on-air formula (AN1200.13)."""
    t_sym = (2 ** sf) / (bw_khz * 1000.0)
    de = 1 if t_sym > 0.016 else 0  # low data-rate optimisation
    h = 0 if explicit_header else 1
    num = 8 * payload_bytes - 4 * sf + 28 + 16 * int(crc) - 20 * h
    n_payload = 8 + max(math.ceil(num / (4 * (sf - 2 * de))) * cr, 0)
    return (preamble + 4.25) * t_sym + n_payload * t_sym


def sensitivity_dbm(sf: int, bw_khz: float, noise_figure_db: float = 6.0) -> float:
    snr_limit = -7.5 - 2.5 * (sf - 7)
    return -174 + 10 * math.log10(bw_khz * 1000) + noise_figure_db + snr_limit


@dataclass
class Delivery:
    data: bytes
    rssi_dbm: float
    snr_db: float
    latency_ms: float
    tx_sim_t: float


@dataclass
class LinkStats:
    sent: int = 0
    lost: int = 0
    skipped_busy: int = 0
    corrupted: int = 0
    delivered: int = 0


class LoRaLink:
    def __init__(self, cfg: LinkConfig, rng: random.Random | None = None):
        self.cfg = cfg
        self.rng = rng or random.Random()
        self.stats = LinkStats()
        self._queue: deque[tuple[float, Delivery]] = deque()
        self._busy_until_sim = -1.0
        self._last_delivery = 0.0
        self.last_rssi = -120.0
        self.last_snr = 0.0
        self.last_airtime_ms = 0.0

    def airtime_s(self, nbytes: int) -> float:
        c = self.cfg
        return lora_airtime_s(nbytes, c.spreading_factor, c.bandwidth_khz, c.coding_rate)

    def utilisation(self, nbytes: int) -> float:
        """Fraction of time the radio is transmitting at the configured frame rate."""
        return self.airtime_s(nbytes) * self.cfg.tx_rate_hz

    def transmit(self, data: bytes, sim_t: float, now: float, distance_m: float) -> None:
        c, g = self.cfg, self.rng
        airtime = self.airtime_s(len(data))
        self.last_airtime_ms = airtime * 1000
        if c.enforce_airtime and sim_t < self._busy_until_sim:
            self.stats.skipped_busy += 1
            return
        self._busy_until_sim = sim_t + airtime
        self.stats.sent += 1

        d_km = max(distance_m, 1.0) / 1000.0
        fspl = 20 * math.log10(d_km) + 20 * math.log10(c.frequency_mhz) + 32.44
        rssi = c.tx_power_dbm + 2.0 - fspl + g.gauss(0, 2.5)  # +2 dBi antennas, fading
        noise_floor = -174 + 10 * math.log10(c.bandwidth_khz * 1000) + 6.0
        snr = rssi - noise_floor
        margin = rssi - sensitivity_dbm(c.spreading_factor, c.bandwidth_khz)
        p_loss = c.packet_loss_pct / 100.0
        if margin < 6:  # fading margin exhausted -> loss rises steeply
            p_loss = max(p_loss, min(1.0, (6 - margin) / 8))
        if g.random() < p_loss:
            self.stats.lost += 1
            return
        if g.random() < c.corruption_pct / 100.0:
            buf = bytearray(data)
            i = g.randrange(3, len(buf))
            buf[i] ^= 1 << g.randrange(8)
            data = bytes(buf)
            self.stats.corrupted += 1

        latency = airtime + (c.base_latency_ms + abs(g.gauss(0, c.jitter_ms))) / 1000.0
        # radio/serial deliver in order: never before the previous frame
        at = max(now + latency, self._last_delivery)
        self._last_delivery = at
        self.last_rssi, self.last_snr = rssi, snr
        self._queue.append((at, Delivery(data, rssi, snr, (at - now) * 1000.0, sim_t)))

    def poll(self, now: float) -> list[Delivery]:
        out = []
        while self._queue and self._queue[0][0] <= now:
            out.append(self._queue.popleft()[1])
        self.stats.delivered += len(out)
        return out

    def reset(self) -> None:
        self._queue.clear()
        self._busy_until_sim = -1.0
        self.stats = LinkStats()
