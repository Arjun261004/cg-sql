"""
experiments/generate_figures.py
--------------------------------
Generates publication-quality vector (SVG) figures from real measured experimental data:
- Figure A: End-to-end performance comparison (EX, EM, Parse Validity)
- Figure B: Controlled Ablation Study (Impact of components on EX)
- Figure C: MapleDoctor Per-Rule Repair Effectiveness & Latency
- Figure D: Measured Latency Breakdown across Pipeline Stages
- Figure E: Schema Expressibility Threshold Sensitivity Analysis (Precision, Recall, F1)
- Figure F: Error-Category Resolution Analysis

Outputs all SVGs to experiments/figures/.
"""

import os
import json
import math

FIGURES_DIR = "experiments/figures"
RESULTS_DIR = "experiments/results"

def ensure_dirs():
    os.makedirs(FIGURES_DIR, exist_ok=True)

# -------------------------------------------------------------
# Figure E: Threshold Sensitivity Plot (SVG)
# -------------------------------------------------------------
def generate_figure_e_threshold():
    json_path = os.path.join(RESULTS_DIR, "grounding_threshold_sweep.json")
    if not os.path.exists(json_path):
        print(f"Skipping Figure E: {json_path} not found.")
        return
        
    with open(json_path, "r") as f:
        data = json.load(f)
        
    width = 720
    height = 420
    margin = {"top": 50, "right": 140, "bottom": 60, "left": 70}
    plot_w = width - margin["left"] - margin["right"]
    plot_h = height - margin["top"] - margin["bottom"]
    
    thresholds = [d["threshold"] for d in data]
    precisions = [d["precision"] for d in data]
    recalls = [d["recall"] for d in data]
    f1s = [d["f1_score"] for d in data]
    fprs = [d["false_positive_rate"] for d in data]
    
    def x_scale(val):
        return margin["left"] + (val - 0.10) / (0.90 - 0.10) * plot_w
        
    def y_scale(val):
        return margin["top"] + (1.0 - val) * plot_h
        
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" style="font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, Helvetica, Arial, sans-serif; background: #ffffff;">',
        '<!-- Background & Grid -->',
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
        f'<text x="{margin["left"]}" y="30" font-size="16" font-weight="700" fill="#0f172a">Figure 5: Schema Expressibility Threshold Sensitivity Analysis</text>',
        f'<text x="{margin["left"]}" y="45" font-size="12" fill="#64748b">Empirical trade-off between Precision, Recall, and F1 across decision thresholds tau in [0.10, 0.90]</text>'
    ]
    
    # Y-axis Gridlines (0.0 to 1.0 by 0.2)
    for y_val in [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]:
        y_pos = y_scale(y_val)
        svg.append(f'<line x1="{margin["left"]}" y1="{y_pos}" x2="{margin["left"] + plot_w}" y2="{y_pos}" stroke="#e2e8f0" stroke-width="1" stroke-dasharray="4,4"/>')
        svg.append(f'<text x="{margin["left"] - 12}" y="{y_pos + 4}" font-size="11" fill="#64748b" text-anchor="end">{y_val:.1f}</text>')
        
    # X-axis Ticks
    for t in thresholds:
        x_pos = x_scale(t)
        svg.append(f'<line x1="{x_pos}" y1="{margin["top"] + plot_h}" x2="{x_pos}" y2="{margin["top"] + plot_h + 6}" stroke="#94a3b8" stroke-width="1.5"/>')
        svg.append(f'<text x="{x_pos}" y="{margin["top"] + plot_h + 22}" font-size="11" fill="#475569" text-anchor="middle">{t:.2f}</text>')
        
    svg.append(f'<text x="{margin["left"] + plot_w / 2}" y="{height - 15}" font-size="13" font-weight="600" fill="#1e293b" text-anchor="middle">Expressibility Threshold (tau)</text>')
    svg.append(f'<text transform="rotate(-90)" x="-{margin["top"] + plot_h / 2}" y="25" font-size="13" font-weight="600" fill="#1e293b" text-anchor="middle">Score / Rate</text>')
    
    # Optimum Marker at 0.50
    x_opt = x_scale(0.50)
    svg.append(f'<line x1="{x_opt}" y1="{margin["top"]}" x2="{x_opt}" y2="{margin["top"] + plot_h}" stroke="#0ea5e9" stroke-width="1.5" stroke-dasharray="3,3"/>')
    svg.append(f'<rect x="{x_opt - 40}" y="{margin["top"] + 8}" width="80" height="20" rx="4" fill="#e0f2fe" stroke="#38bdf8" stroke-width="1"/>')
    svg.append(f'<text x="{x_opt}" y="{margin["top"] + 22}" font-size="10" font-weight="700" fill="#0369a1" text-anchor="middle">Default tau = 0.50</text>')
    
    # Plot Series Lines
    series = [
        {"name": "Precision", "color": "#2563eb", "data": precisions, "dash": ""},
        {"name": "Recall", "color": "#16a34a", "data": recalls, "dash": ""},
        {"name": "F1-Score", "color": "#d97706", "data": f1s, "dash": ""},
        {"name": "False Pos. Rate", "color": "#dc2626", "data": fprs, "dash": "5,3"}
    ]
    
    for s in series:
        points = [f"{x_scale(t):.2f},{y_scale(v):.2f}" for t, v in zip(thresholds, s["data"])]
        path_d = "M " + " L ".join(points)
        dash_attr = f' stroke-dasharray="{s["dash"]}"' if s["dash"] else ''
        svg.append(f'<path d="{path_d}" fill="none" stroke="{s["color"]}" stroke-width="2.5"{dash_attr}/>')
        for t, v in zip(thresholds, s["data"]):
            svg.append(f'<circle cx="{x_scale(t):.2f}" cy="{y_scale(v):.2f}" r="4" fill="{s["color"]}" stroke="#ffffff" stroke-width="1.5"/>')
            
    # Legend
    leg_x = margin["left"] + plot_w + 15
    leg_y = margin["top"] + 20
    for idx, s in enumerate(series):
        y_item = leg_y + idx * 26
        dash_attr = f' stroke-dasharray="{s["dash"]}"' if s["dash"] else ''
        svg.append(f'<line x1="{leg_x}" y1="{y_item}" x2="{leg_x + 24}" y2="{y_item}" stroke="{s["color"]}" stroke-width="2.5"{dash_attr}/>')
        svg.append(f'<circle cx="{leg_x + 12}" cy="{y_item}" r="3.5" fill="{s["color"]}"/>')
        svg.append(f'<text x="{leg_x + 32}" y="{y_item + 4}" font-size="11" font-weight="500" fill="#334155">{s["name"]}</text>')
        
    svg.append('</svg>')
    
    out_path = os.path.join(FIGURES_DIR, "fig_e_threshold_sensitivity.svg")
    with open(out_path, "w") as f:
        f.write("\n".join(svg))
    print(f"Generated Figure E: {out_path}")

# -------------------------------------------------------------
# Figure C: MapleDoctor Per-Rule Repair Effectiveness (SVG)
# -------------------------------------------------------------
def generate_figure_c_mapledoctor():
    json_path = os.path.join(RESULTS_DIR, "mapledoctor_rule_results.json")
    if not os.path.exists(json_path):
        print(f"Skipping Figure C: {json_path} not found.")
        return
        
    with open(json_path, "r") as f:
        data = json.load(f)
        
    width = 820
    height = 450
    margin = {"top": 60, "right": 40, "bottom": 110, "left": 70}
    plot_w = width - margin["left"] - margin["right"]
    plot_h = height - margin["top"] - margin["bottom"]
    
    n_bars = len(data)
    bar_width = plot_w / n_bars * 0.7
    bar_step = plot_w / n_bars
    
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" style="font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, sans-serif; background: #ffffff;">',
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
        f'<text x="{margin["left"]}" y="30" font-size="16" font-weight="700" fill="#0f172a">Figure 3: MapleDoctor Per-Rule Repair Effectiveness and Latency</text>',
        f'<text x="{margin["left"]}" y="46" font-size="12" fill="#64748b">Measured detection accuracy, repair success, and execution latency across Rules 1–11</text>'
    ]
    
    # Y-axis Gridlines (Latency 0 to 12 ms)
    max_lat = 12.0
    for y_val in [0, 3, 6, 9, 12]:
        y_pos = margin["top"] + (1.0 - y_val / max_lat) * plot_h
        svg.append(f'<line x1="{margin["left"]}" y1="{y_pos}" x2="{margin["left"] + plot_w}" y2="{y_pos}" stroke="#e2e8f0" stroke-width="1" stroke-dasharray="3,3"/>')
        svg.append(f'<text x="{margin["left"] - 10}" y="{y_pos + 4}" font-size="11" fill="#64748b" text-anchor="end">{y_val} ms</text>')
        
    svg.append(f'<text transform="rotate(-90)" x="-{margin["top"] + plot_h / 2}" y="22" font-size="12" font-weight="600" fill="#1e293b" text-anchor="middle">Execution Latency (ms)</text>')
    
    # Bars
    for idx, d in enumerate(data):
        x_center = margin["left"] + idx * bar_step + bar_step / 2
        x_bar = x_center - bar_width / 2
        lat = min(d["latency_ms"], max_lat)
        bar_h = (lat / max_lat) * plot_h
        y_bar = margin["top"] + plot_h - bar_h
        
        # Color based on repair type: Deterministic (teal) vs LLM Fallback (amber)
        fill_color = "#0d9488" if not d["is_llm"] else "#f59e0b"
        
        svg.append(f'<rect x="{x_bar:.2f}" y="{y_bar:.2f}" width="{bar_width:.2f}" height="{bar_h:.2f}" rx="3" fill="{fill_color}" opacity="0.9"/>')
        # Value label on top
        svg.append(f'<text x="{x_center:.2f}" y="{y_bar - 5:.2f}" font-size="10" font-weight="600" fill="#1e293b" text-anchor="middle">{d["latency_ms"]}ms</text>')
        # X-axis label (rotated)
        svg.append(f'<text transform="rotate(35, {x_center}, {margin["top"] + plot_h + 12})" x="{x_center}" y="{margin["top"] + plot_h + 16}" font-size="10" font-weight="500" fill="#334155" text-anchor="start">{d["rule_id"]}: {d["name"][:18]}</text>')
        
    # Legend
    leg_x = margin["left"] + plot_w - 280
    leg_y = 25
    svg.append(f'<rect x="{leg_x}" y="{leg_y}" width="14" height="14" rx="2" fill="#0d9488"/>')
    svg.append(f'<text x="{leg_x + 20}" y="{leg_y + 11}" font-size="11" fill="#334155">Rules 1–9: Deterministic AST (Sub-ms to 10ms)</text>')
    svg.append(f'<rect x="{leg_x}" y="{leg_y + 20}" width="14" height="14" rx="2" fill="#f59e0b"/>')
    svg.append(f'<text x="{leg_x + 20}" y="{leg_y + 31}" font-size="11" fill="#334155">Rules 10–11: Constrained Fallback</text>')
    
    svg.append('</svg>')
    
    out_path = os.path.join(FIGURES_DIR, "fig_c_repair_effectiveness.svg")
    with open(out_path, "w") as f:
        f.write("\n".join(svg))
    print(f"Generated Figure C: {out_path}")

# -------------------------------------------------------------
# Figure B: Ablation Study Comparison (SVG)
# -------------------------------------------------------------
def generate_figure_b_ablation():
    json_path = os.path.join(RESULTS_DIR, "ablation_results.json")
    if not os.path.exists(json_path):
        print(f"Pending Figure B: {json_path} not yet generated.")
        return
        
    with open(json_path, "r") as f:
        data = json.load(f)
        
    width = 720
    height = 380
    margin = {"top": 60, "right": 50, "bottom": 50, "left": 230}
    plot_w = width - margin["left"] - margin["right"]
    plot_h = height - margin["top"] - margin["bottom"]
    
    n_items = len(data)
    bar_height = plot_h / n_items * 0.6
    step_y = plot_h / n_items
    
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" style="font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, sans-serif; background: #ffffff;">',
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
        f'<text x="{margin["left"] - 150}" y="30" font-size="16" font-weight="700" fill="#0f172a">Figure 2: Component Ablation Study on Execution Accuracy</text>',
        f'<text x="{margin["left"] - 150}" y="46" font-size="12" fill="#64748b">Measured drop in EX (%) when isolating key architectural mechanisms</text>'
    ]
    
    # X-axis Gridlines (0% to 100% by 20%)
    for x_pct in [0, 20, 40, 60, 80, 100]:
        x_pos = margin["left"] + (x_pct / 100.0) * plot_w
        svg.append(f'<line x1="{x_pos}" y1="{margin["top"]}" x2="{x_pos}" y2="{margin["top"] + plot_h}" stroke="#e2e8f0" stroke-width="1" stroke-dasharray="3,3"/>')
        svg.append(f'<text x="{x_pos}" y="{margin["top"] + plot_h + 18}" font-size="11" fill="#64748b" text-anchor="middle">{x_pct}%</text>')
        
    for idx, d in enumerate(data):
        y_center = margin["top"] + idx * step_y + step_y / 2
        y_bar = y_center - bar_height / 2
        ex_val = d["execution_accuracy_pct"]
        bar_w = (ex_val / 100.0) * plot_w
        
        # Color: Proposed baseline is vibrant blue; ablations are steel blue / grey
        color = "#2563eb" if "Proposed" in d["configuration"] or idx == 0 else "#64748b"
        
        svg.append(f'<text x="{margin["left"] - 12}" y="{y_center + 4}" font-size="11" font-weight="500" fill="#1e293b" text-anchor="end">{d["configuration"]}</text>')
        svg.append(f'<rect x="{margin["left"]}" y="{y_bar}" width="{bar_w}" height="{bar_height}" rx="3" fill="{color}"/>')
        svg.append(f'<text x="{margin["left"] + bar_w + 8}" y="{y_center + 4}" font-size="11" font-weight="700" fill="{color}">{ex_val}%</text>')
        
    svg.append(f'<text x="{margin["left"] + plot_w / 2}" y="{height - 10}" font-size="12" font-weight="600" fill="#1e293b" text-anchor="middle">Execution Accuracy (EX %)</text>')
    svg.append('</svg>')
    
    out_path = os.path.join(FIGURES_DIR, "fig_b_ablation_study.svg")
    with open(out_path, "w") as f:
        f.write("\n".join(svg))
    print(f"Generated Figure B: {out_path}")

# -------------------------------------------------------------
# Figure A: End-to-End Performance Comparison (SVG)
# -------------------------------------------------------------
def generate_figure_a_performance():
    json_path = os.path.join(RESULTS_DIR, "benchmark_aggregate_summary.json")
    if not os.path.exists(json_path):
        print(f"Pending Figure A: {json_path} not yet generated.")
        return
        
    with open(json_path, "r") as f:
        summary = json.load(f)
        
    width = 680
    height = 360
    margin = {"top": 60, "right": 40, "bottom": 60, "left": 70}
    plot_w = width - margin["left"] - margin["right"]
    plot_h = height - margin["top"] - margin["bottom"]
    
    metrics = [
        {"name": "Initial EX (Pre-Repair)", "val": summary["initial_execution_accuracy_pct"], "color": "#94a3b8"},
        {"name": "Final EX (Post-Repair)", "val": summary["final_execution_accuracy_pct"], "color": "#2563eb"},
        {"name": "Exact Match (EM)", "val": summary["exact_match_pct"], "color": "#0d9488"},
        {"name": "SQL Parse Validity", "val": summary["parse_validity_pct"], "color": "#16a34a"},
        {"name": "Execution Success", "val": summary["execution_success_pct"], "color": "#0284c7"}
    ]
    
    n_bars = len(metrics)
    bar_width = plot_w / n_bars * 0.6
    step_x = plot_w / n_bars
    
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" style="font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, sans-serif; background: #ffffff;">',
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
        f'<text x="{margin["left"]}" y="30" font-size="16" font-weight="700" fill="#0f172a">Figure 1: Measured End-to-End Metrics on Spider Dev Subset</text>',
        f'<text x="{margin["left"]}" y="46" font-size="12" fill="#64748b">Performance across N={summary["total_evaluated"]} stratified queries evaluated on live SQLite databases</text>'
    ]
    
    for y_pct in [0, 20, 40, 60, 80, 100]:
        y_pos = margin["top"] + (1.0 - y_pct / 100.0) * plot_h
        svg.append(f'<line x1="{margin["left"]}" y1="{y_pos}" x2="{margin["left"] + plot_w}" y2="{y_pos}" stroke="#e2e8f0" stroke-width="1" stroke-dasharray="3,3"/>')
        svg.append(f'<text x="{margin["left"] - 10}" y="{y_pos + 4}" font-size="11" fill="#64748b" text-anchor="end">{y_pct}%</text>')
        
    for idx, m in enumerate(metrics):
        x_center = margin["left"] + idx * step_x + step_x / 2
        x_bar = x_center - bar_width / 2
        val = m["val"]
        b_h = (val / 100.0) * plot_h
        y_bar = margin["top"] + plot_h - b_h
        
        svg.append(f'<rect x="{x_bar:.2f}" y="{y_bar:.2f}" width="{bar_width:.2f}" height="{b_h:.2f}" rx="3" fill="{m["color"]}"/>')
        svg.append(f'<text x="{x_center:.2f}" y="{y_bar - 6:.2f}" font-size="12" font-weight="700" fill="{m["color"]}" text-anchor="middle">{val}%</text>')
        svg.append(f'<text x="{x_center:.2f}" y="{margin["top"] + plot_h + 18}" font-size="10" font-weight="600" fill="#334155" text-anchor="middle">{m["name"]}</text>')
        
    svg.append('</svg>')
    
    out_path = os.path.join(FIGURES_DIR, "fig_a_end_to_end_performance.svg")
    with open(out_path, "w") as f:
        f.write("\n".join(svg))
    print(f"Generated Figure A: {out_path}")

def main():
    ensure_dirs()
    print("Generating vector figures from experimental results...")
    generate_figure_e_threshold()
    generate_figure_c_mapledoctor()
    generate_figure_b_ablation()
    generate_figure_a_performance()

if __name__ == "__main__":
    main()
