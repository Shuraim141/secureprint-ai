"""Pure-logic tests for the G-code safety analyzer. No web framework or database."""
import pathlib

from app.manufacturing.gcode import MAX_LINE_LENGTH, MAX_LINES, GCodeTooLargeError, analyze_gcode

SAMPLES_DIR = pathlib.Path(__file__).resolve().parents[2] / "manufacturing" / "gcode"


def raises(exc_type, func, *args, **kwargs):
    try:
        func(*args, **kwargs)
    except exc_type as error:
        return error
    raise AssertionError(f"expected {exc_type.__name__}")


def sample(name: str) -> str:
    return (SAMPLES_DIR / f"{name}.gcode").read_text()


# ---------------- the four required demo files ----------------
def test_safe_sample_is_reported_safe_with_no_findings():
    result = analyze_gcode(sample("safe"))
    assert result["safe"] is True and result["risk"] == "NONE" and result["findings"] == []
    assert result["stats"]["max_nozzle_temp_c"] == 205.0
    assert result["stats"]["max_bed_temp_c"] == 60.0


def test_malicious_temperature_sample_is_flagged_high_risk():
    result = analyze_gcode(sample("malicious_temperature"))
    assert result["safe"] is False and result["risk"] == "HIGH"
    codes = {f["code"] for f in result["findings"]}
    assert "EXCESSIVE_NOZZLE_TEMPERATURE" in codes and "EXCESSIVE_BED_TEMPERATURE" in codes
    assert result["stats"]["max_nozzle_temp_c"] == 280.0


def test_malicious_speed_sample_is_flagged_high_risk():
    result = analyze_gcode(sample("malicious_speed"))
    assert result["safe"] is False and result["risk"] == "HIGH"
    assert any(f["code"] == "EXCESSIVE_FEED_RATE" for f in result["findings"])
    assert result["stats"]["max_feed_rate_mm_s"] == 500.0


def test_suspicious_command_sample_is_flagged_high_risk():
    result = analyze_gcode(sample("suspicious_command"))
    assert result["safe"] is False and result["risk"] == "HIGH"
    codes = [f["code"] for f in result["findings"]]
    assert codes.count("DENYLISTED_COMMAND") == 3
    messages = " ".join(f["message"] for f in result["findings"])
    assert "M115" in messages and "M28" in messages and "M997" in messages


# ---------------- the S0 heater-off regression (real bug caught before shipping) ----------------
def test_heater_off_s0_is_never_flagged_as_out_of_range():
    text = "M104 S0\nM140 S0\nM109 S0\nM190 S0\n"
    result = analyze_gcode(text)
    assert result["safe"] is True and result["findings"] == []


def test_heater_negative_or_low_but_nonzero_temperature_still_flagged():
    # a nonzero but very low target (e.g. 5C) is NOT "off" and should still be flagged
    result = analyze_gcode("M104 S5\n")
    assert any(f["code"] == "NOZZLE_TEMPERATURE_OUT_OF_RANGE" for f in result["findings"])


# ---------------- hardening ----------------
def test_oversized_line_is_rejected():
    text = "M104 S205\n" + ("G1 X1" * 100) + "\n"
    result = analyze_gcode(text)
    assert result["risk"] == "HIGH"
    assert any(f["code"] == "OVERSIZED_LINE" for f in result["findings"])


def test_non_printable_content_is_rejected():
    result = analyze_gcode("M104 S205\nG1 X10\x00\x01Y10\n")
    assert any(f["code"] == "NON_PRINTABLE_CONTENT" for f in result["findings"])


def test_malformed_parameters_are_flagged_not_crashed():
    result = analyze_gcode("M104 SabcXyz\n")
    assert any(f["code"] == "MALFORMED_PARAMETERS" for f in result["findings"])


def test_empty_file_is_flagged():
    result = analyze_gcode("; just a comment\n\n")
    assert any(f["code"] == "EMPTY_FILE" for f in result["findings"])


def test_missing_preheat_before_extrusion_is_flagged():
    result = analyze_gcode("G28\nG1 X10 Y10 E5 F1200\n")
    assert any(f["code"] == "MISSING_PREHEAT" for f in result["findings"])
    # but a file that DOES preheat first must not trigger it
    ok = analyze_gcode("M104 S205\nG28\nG1 X10 Y10 E5 F1200\n")
    assert not any(f["code"] == "MISSING_PREHEAT" for f in ok["findings"])


def test_abnormal_single_move_is_flagged():
    result = analyze_gcode("G28\nG1 X0 Y0\nG1 X900 Y0\n")  # 900mm jump: no consumer printer is this big
    assert any(f["code"] == "ABNORMAL_MOVEMENT" for f in result["findings"])


def test_denylisted_commands_all_detected():
    from app.manufacturing.gcode import DENYLISTED_COMMANDS
    for command in DENYLISTED_COMMANDS:
        result = analyze_gcode(f"{command}\n")
        assert any(f["code"] == "DENYLISTED_COMMAND" for f in result["findings"]), command
    assert "M112" not in DENYLISTED_COMMANDS  # emergency stop must remain allowed


def test_oversized_file_raises_before_analysis():
    huge = "\n".join(f"G1 X{i}" for i in range(MAX_LINES + 1))
    raises(GCodeTooLargeError, analyze_gcode, huge)
    huge_bytes = "G1 X1 " * ((MAX_LINES * MAX_LINE_LENGTH) // 6 + 10)
    raises(GCodeTooLargeError, analyze_gcode, huge_bytes)


# ---------------- risk severity ordering ----------------
def test_risk_is_the_worst_finding_severity():
    only_medium = analyze_gcode("G28\nG1 X10 Y10 E5 F1200\n")  # MISSING_PREHEAT = MEDIUM
    assert only_medium["risk"] == "MEDIUM" and only_medium["safe"] is False
    mixed = analyze_gcode("M997\nG28\nG1 X10 Y10 E5 F1200\n")  # HIGH + MEDIUM present
    assert mixed["risk"] == "HIGH"


def test_feed_rate_conversion_from_mm_per_minute_to_mm_per_second():
    # F is mm/MIN in real G-code; 3000 mm/min = 50 mm/s, inside the 30-80 safe range
    result = analyze_gcode("M104 S205\nG1 X10 Y10 E5 F3000\n")
    assert result["stats"]["max_feed_rate_mm_s"] == 50.0
    assert result["safe"] is True
