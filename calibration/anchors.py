"""The thirteen anchorable registries.

Source: UCSRS v1.0, Journal of Cardiothoracic Surgery 2026, Table 1 (Section 6),
"Published AUC and O/E calibration statistics across 14 international registries".

Thirteen of the fourteen carry a numeric published EuroSCORE II O/E and are therefore
anchorable. The fourteenth, Wang et al. (China, n=3,479), reports EuroSCORE II
calibration as "underpredicted (Hosmer-Lemeshow p<0.0001)" with no numeric O/E, so no
target mean can be formed for it and it is excluded -- this is the same thirteen used
for v2.1.

Published STS-PROM O/E exists for twelve of the thirteen; SWEDEHEART reports EuroSCORE II
only (CABG cohort). STS-PROM is carried here for reference and is not used to anchor:
the anchoring dial is tuned on EuroSCORE II, per the method of record.

  target mean predicted risk = published observed mortality / published EuroSCORE II O/E
"""

REGISTRIES = [
    # name,            country,    n,        oe_esii, oe_sts, obs_pct
    ("STS ACSD",       "USA",      8_300_000, 0.72,   1.02,   2.4),
    ("CMS Medicare",   "USA",      2_100_000, 0.68,   1.05,   3.1),
    ("SWEDEHEART",     "Sweden",   14_118,    0.58,   None,   1.5),
    ("KROK",           "Poland",   44_172,    1.10,   1.05,   4.1),
    ("German Registry","Germany",  600_000,   0.98,   0.95,   3.2),
    ("BCIS/NICOR",     "UK",       250_000,   0.85,   1.08,   2.8),
    ("ANZCTS",         "Aus/NZ",   120_000,   0.79,   1.03,   2.6),
    ("JCVSD",          "Japan",    340_000,   1.42,   1.89,   4.1),
    ("Indian cohort",  "India",    4_895,     0.79,   1.25,   1.5),
    ("Brazilian",      "Brazil",   438,       1.59,   3.60,   4.3),
    ("Turkish cohort", "Turkey",   468,       0.83,   1.57,   5.3),
    ("EuroHeart",      "Europe",   650_000,   0.91,   1.12,   3.5),
    ("Korean Registry","S. Korea", 280_000,   1.28,   1.74,   3.8),
]


def table():
    """Returns the anchor list with the derived target mean predicted risk."""
    out = []
    for name, country, n, oe_esii, oe_sts, obs in REGISTRIES:
        out.append({
            "name": name, "country": country, "n_published": n,
            "oe_esii_published": oe_esii, "oe_sts_published": oe_sts,
            "observed_mortality_pct": obs,
            "target_mean_esii_pct": obs / oe_esii,
        })
    return out


if __name__ == "__main__":
    for r in table():
        print(f"{r['name']:<17} {r['country']:<9} obs {r['observed_mortality_pct']:.1f}%  "
              f"ESII O/E {r['oe_esii_published']:.2f}  -> target mean ESII "
              f"{r['target_mean_esii_pct']:.3f}%")
