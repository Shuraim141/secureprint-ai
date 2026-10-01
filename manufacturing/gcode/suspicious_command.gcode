; SecurePrint AI demo: injected commands with no place in a normal print job
M140 S60
M104 S205
M190 S60
M109 S205
G28
G1 Z0.2 F300
G1 X10 Y10 F3000
G1 X50 Y10 E5 F1200
M115                      ; ATTACK: firmware reconnaissance query
M28 config.g               ; ATTACK: begin writing to a system/config file over SD
M997                       ; ATTACK: trigger a firmware update from an untrusted source
G1 X50 Y50 E10 F1200
M104 S0
M140 S0
M84
