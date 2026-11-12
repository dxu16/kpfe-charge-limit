The KONKR Pocket FIT Elite can report a latched `Over voltage` fault after the native firmware limiter lowers its float-voltage target at a partial charge limit. [Issue #883](https://github.com/armada-os/armada/issues/883)

Apply the existing charge thresholds in Linux and use the firmware's charge-rate command (`0x06`) to stop and resume charging. Battery and USB notifications handle transitions, including during `s2idle`. The exact KPFE device-tree match scopes the change to this model.

A fresh USB-PD attachment during a charge-limit hold can stay at 5 V. On an eligible awake attachment, briefly release the stop so firmware can negotiate higher input voltage. Reapply the stop when higher voltage is confirmed, the cable is removed, or the 2.5-second polling window expires. Firmware response delays can extend stop confirmation.

Validated on one KPFE with Linux 7.2.6. The driver stopped at the upper threshold, resumed at the lower threshold after reconnection, and issued a threshold stop during `s2idle`. In the installed build, reconnecting at 85% negotiated 9 V after a 0.75-second charge window, then held for ten minutes with charging disabled and Good health. The 5 V non-PD source skipped negotiation. Cable removal ended the window early, and a suspend request during negotiation completed after firmware acknowledged the stop.

The 5 V-only USB-PD timeout and late firmware replies were tested in simulation. Battery-service restart recovery and a full Armada kernel package build remain unverified.

[Investigation and test evidence](https://github.com/dxu16/kpfe-charge-limit)
