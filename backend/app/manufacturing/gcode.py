"""G-code safety analyzer (Module H): a real line-by-line parser, not a filename check.

Reuses the same safe operating ranges as predictive quality analytics (Module A3) and the
manufacturing anomaly detector, so "safe" means the same thing everywhere in the platform.

Checks implemented: excessive nozzle/bed temperature, abnormal feed rate, an oversized or
non-ASCII line (buffer-overflow / injection style attempts), a denylist of commands with no
place in an ordinary consumer FDM print job, and a large single-move jump that could indicate
a corrupted or tampered toolpath. This is a rule-based MVP; a production system would also
run a full kinematic/collision simulation.
"""
import re
from dataclasses import dataclass, field

from app.ml.process_dataset import SAFE_RANGES

MAX_LINE_LENGTH = 256
MAX_LINES = 200_000
MAX_SINGLE_MOVE_MM = 500.0  # larger than any consumer FDM printer's build volume

# Commands with no legitimate place in an ordinary print job uploaded by an end user.
# M112 (emergency stop) is deliberately NOT denylisted: it is a real safety command.
DENYLISTED_COMMANDS = {
    "M997": "Firmware update trigger",
    "M999": "Firmware reset",
    "M500": "Save settings to EEPROM (persists unexpected values across prints)",
    "M502": "Restore factory default settings",
    "M28": "Begin SD card file write (can overwrite firmware/config files)",
    "M29": "End SD card file write",
    "M115": "Firmware info query (reconnaissance, not a print command)",
}

_LINE_RE = re.compile(r"^[ -~]*$")  # printable ASCII only (blocks control/binary injection)
_COMMENT_RE = re.compile(r";.*$")
_PARAM_RE = re.compile(r"([A-Za-z])(-?[0-9]*\.?[0-9]+)")


class GCodeTooLargeError(ValueError):
    pass


@dataclass
class GCodeStats:
    total_lines: int = 0
    command_lines: int = 0
    move_commands: int = 0
    max_nozzle_temp_c: float | None = None
    max_bed_temp_c: float | None = None
    max_feed_rate_mm_s: float | None = None
    max_single_move_mm: float = 0.0
    commands_seen: dict[str, int] = field(default_factory=dict)


@dataclass
class Finding:
    line: int
    severity: str  # LOW | MEDIUM | HIGH
    code: str
    message: str


def _severity_rank(severity: str) -> int:
    return {"LOW": 0, "MEDIUM": 1, "HIGH": 2}.get(severity, 0)


def _overall_risk(findings: list[Finding]) -> str:
    if not findings:
        return "NONE"
    worst = max(_severity_rank(f.severity) for f in findings)
    return {0: "LOW", 1: "MEDIUM", 2: "HIGH"}[worst]


def _parse_params(rest: str) -> dict[str, float]:
    return {letter.upper(): float(value) for letter, value in _PARAM_RE.findall(rest)}


def analyze_gcode(text: str) -> dict:
    """Analyze raw G-code text. Returns a JSON-safe report with 'safe', 'risk', 'findings',
    'stats'. Raises GCodeTooLargeError for pathologically large input (caller maps to 413/422)."""
    if len(text) > MAX_LINES * MAX_LINE_LENGTH:
        raise GCodeTooLargeError("G-code file is too large to analyze")
    lines = text.splitlines()
    if len(lines) > MAX_LINES:
        raise GCodeTooLargeError(f"G-code has too many lines (limit {MAX_LINES})")

    stats = GCodeStats()
    findings: list[Finding] = []
    last_xyz: dict[str, float] = {}
    saw_extrusion = False
    saw_preheat = False

    for line_no, raw_line in enumerate(lines, start=1):
        stats.total_lines += 1
        if len(raw_line) > MAX_LINE_LENGTH:
            findings.append(Finding(line_no, "HIGH", "OVERSIZED_LINE",
                                    f"Line exceeds {MAX_LINE_LENGTH} characters"))
            continue
        if not _LINE_RE.match(raw_line):
            findings.append(Finding(line_no, "HIGH", "NON_PRINTABLE_CONTENT",
                                    "Line contains non-printable or non-ASCII bytes"))
            continue

        line = _COMMENT_RE.sub("", raw_line).strip()
        if not line:
            continue
        parts = line.split(None, 1)
        command = parts[0].upper()
        rest = parts[1] if len(parts) > 1 else ""
        stats.command_lines += 1
        stats.commands_seen[command] = stats.commands_seen.get(command, 0) + 1

        if command in DENYLISTED_COMMANDS:
            findings.append(Finding(line_no, "HIGH", "DENYLISTED_COMMAND",
                                    f"{command}: {DENYLISTED_COMMANDS[command]}"))
            continue

        params = _parse_params(rest)
        # _parse_params only ever extracts well-formed "letter+number" tokens, so garbage text
        # after a command that normally takes one (e.g. "M104 SabcXyz") yields an EMPTY dict
        # rather than raising -- silently treating it as "no parameters" would hide a malformed
        # line, so detect that case explicitly for the commands we actually interpret.
        expects_params = command in {"M104", "M109", "M140", "M190", "G0", "G1"}
        if expects_params and rest.strip() and not params:
            findings.append(Finding(line_no, "MEDIUM", "MALFORMED_PARAMETERS",
                                    f"Could not parse parameters for {command}: {rest.strip()!r}"))
            continue

        if command in {"M104", "M109"} and "S" in params:  # set/wait nozzle temperature
            temp = params["S"]
            stats.max_nozzle_temp_c = max(stats.max_nozzle_temp_c or temp, temp)
            saw_preheat = True
            low, high = SAFE_RANGES["nozzle_temp_c"]
            # S0 (and any negative value clamped to it by firmware) means "heater off", which is
            # always safe -- most prints end with M104 S0, so 0 must never be flagged as "too cold".
            if temp > 0:
                if temp > high * 1.15:
                    findings.append(Finding(line_no, "HIGH", "EXCESSIVE_NOZZLE_TEMPERATURE",
                                            f"{command} sets nozzle to {temp}C (safe range {low}-{high}C)"))
                elif not (low <= temp <= high):
                    findings.append(Finding(line_no, "MEDIUM", "NOZZLE_TEMPERATURE_OUT_OF_RANGE",
                                            f"{command} sets nozzle to {temp}C (safe range {low}-{high}C)"))

        elif command in {"M140", "M190"} and "S" in params:  # set/wait bed temperature
            temp = params["S"]
            stats.max_bed_temp_c = max(stats.max_bed_temp_c or temp, temp)
            low, high = SAFE_RANGES["bed_temp_c"]
            # S0 means "heater off", which is always safe (see the nozzle-temperature comment above).
            if temp > 0:
                if temp > high * 1.15:
                    findings.append(Finding(line_no, "HIGH", "EXCESSIVE_BED_TEMPERATURE",
                                            f"{command} sets bed to {temp}C (safe range {low}-{high}C)"))
                elif not (low <= temp <= high):
                    findings.append(Finding(line_no, "MEDIUM", "BED_TEMPERATURE_OUT_OF_RANGE",
                                            f"{command} sets bed to {temp}C (safe range {low}-{high}C)"))

        elif command in {"G0", "G1"}:
            stats.move_commands += 1
            if "E" in params and params["E"] > 0:
                saw_extrusion = True
            if "F" in params:  # feed rate is mm/MIN in G-code; convert to mm/s
                feed_mm_s = params["F"] / 60.0
                stats.max_feed_rate_mm_s = max(stats.max_feed_rate_mm_s or feed_mm_s, feed_mm_s)
                low, high = SAFE_RANGES["speed_mm_s"]
                if feed_mm_s > high * 2:
                    findings.append(Finding(line_no, "HIGH", "EXCESSIVE_FEED_RATE",
                                            f"{command} feed rate {feed_mm_s:.0f} mm/s "
                                            f"(safe range {low}-{high} mm/s)"))
                elif feed_mm_s > high:
                    findings.append(Finding(line_no, "MEDIUM", "FEED_RATE_OUT_OF_RANGE",
                                            f"{command} feed rate {feed_mm_s:.0f} mm/s "
                                            f"(safe range {low}-{high} mm/s)"))
            axes = {k: v for k, v in params.items() if k in "XYZ"}
            if axes:
                jump = max((abs(v - last_xyz.get(k, v)) for k, v in axes.items()), default=0.0)
                stats.max_single_move_mm = max(stats.max_single_move_mm, jump)
                if jump > MAX_SINGLE_MOVE_MM:
                    findings.append(Finding(line_no, "HIGH", "ABNORMAL_MOVEMENT",
                                            f"{command} moves {jump:.0f} mm in a single command "
                                            f"(limit {MAX_SINGLE_MOVE_MM} mm)"))
                last_xyz.update(axes)

    if saw_extrusion and not saw_preheat:
        findings.append(Finding(0, "MEDIUM", "MISSING_PREHEAT",
                                "File extrudes material but never sets a nozzle temperature "
                                "(M104/M109)"))
    if stats.command_lines == 0:
        findings.append(Finding(0, "MEDIUM", "EMPTY_FILE", "No recognizable G-code commands found"))

    risk = _overall_risk(findings)
    return {
        "safe": risk not in {"MEDIUM", "HIGH"}, "risk": risk,
        "findings": [f.__dict__ for f in sorted(findings, key=lambda f: f.line)],
        "stats": stats.__dict__,
    }
