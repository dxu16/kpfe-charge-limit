# Superseded RFC2

RFC2’s OEM bypass recovery passed RAM tests, but the first installed hold failed when a near-zero current reading became positive. RFC3 checked about every five seconds and later failed charger attachment during `s2idle`. This archive preserves RFC2. The final driver uses firmware command `0x06`. [Final patch and design](../../experimental/charge-rate-policy/README.md)
