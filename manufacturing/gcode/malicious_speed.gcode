; SecurePrint AI demo: tampered feed rate (excessive print speed)
M140 S60
M104 S205
M190 S60
M109 S205
G28
G1 Z0.2 F300
G1 X10 Y10 F3000
G1 X50 Y10 E5 F30000     ; ATTACK: 500 mm/s, far above the safe 30-80 mm/s range
G1 X50 Y50 E10 F30000
G1 X10 Y50 E15 F1200
M104 S0
M140 S0
M84
