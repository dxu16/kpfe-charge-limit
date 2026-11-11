The KONKR Pocket FIT Elite can report a latched `Over voltage` fault several minutes after reaching a partial charge limit. The native firmware limiter lowers its float-voltage target before the fault appears.

Use the firmware's charge-rate command to stop and resume charging on KPFE. Keep the existing charge thresholds and handle transitions through battery and USB notifications, including during `s2idle`. The exact KPFE device-tree match scopes the change to this model.

Validated on one KPFE with Linux 7.2.6. Charging stayed off after reconnecting above the limit and during a ten-minute hold on the installed build. It resumed at the lower threshold after reconnecting and stopped at the upper threshold. The stop command was sent before wake when charging reached the limit in `s2idle`. After plugging in during `s2idle`, the charger was disabled on the first reading after wake.

Battery-service restart recovery and a full Armada kernel package build remain unverified.
