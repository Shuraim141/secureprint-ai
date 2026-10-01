; SecurePrint AI demo: a normal, safe print sequence
M140 S60          ; set bed temperature
M104 S205         ; set nozzle temperature
M190 S60          ; wait for bed
M109 S205         ; wait for nozzle
G28               ; home all axes
G1 Z0.2 F300
G1 X10 Y10 F3000
G1 X50 Y10 E5 F1200
G1 X50 Y50 E10 F1200
G1 X10 Y50 E15 F1200
G1 X10 Y10 E20 F1200
G1 Z0.4 F300
G1 X50 Y10 E25 F1200
M104 S0            ; nozzle off
M140 S0            ; bed off
G28 X0 Y0
M84                ; disable motors
