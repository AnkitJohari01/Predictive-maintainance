"""Writes a realistic sample CSV: python scripts/make_sample.py out.csv"""
import random, sys, datetime as dt
random.seed(7); M = ["P-203", "CV-08", "C-07", "M-114", "F-021", "T-005"]
rows = ["timestamp,machine_id,vibration_mm_s,bearing_temp_c,pressure_bar,motor_current_a,failure"]
for d in range(30):
    for i, m in enumerate(M):
        v = 2 + random.uniform(-.2, .2) + ((d - 20) * .5 if i == 0 and d > 20 else 0)
        t = 62 + random.uniform(-1.5, 1.5) + ((d - 18) * 2.1 if i == 1 and d > 18 else 0)
        p = 6.2 + random.uniform(-.1, .1) - ((d - 22) * .2 if i == 2 and d > 22 else 0)
        rows.append(f"{dt.date(2026, 9, 22) + dt.timedelta(d)},{m},{v:.2f},{t:.1f},{p:.2f},{38 + random.uniform(-1, 1):.1f},{int(i == 3 and d == 5)}")
open(sys.argv[1] if len(sys.argv) > 1 else "sample_telemetry.csv", "w").write("\n".join(rows))
