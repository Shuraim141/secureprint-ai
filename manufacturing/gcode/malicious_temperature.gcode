; SecurePrint AI demo: tampered nozzle/bed temperatures (thermal-runaway style attack)
M140 S60
M104 S280          ; ATTACK: nozzle far above the safe 190-220C range
M190 S60
M109 S280
G28
G1 Z0.2 F300
G1 X10 Y10 F3000
G1 X50 Y10 E5 F1200
M140 S130          ; ATTACK: bed far above the safe 50-70C range
G1 X50 Y50 E10 F1200
M104 S0
M140 S0
M84
