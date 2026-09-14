#!/usr/bin/env python3
"""Score Calculator — 加权评分计算器

从 JSON 评分数据计算各维度得分和加权总分。
纯数学计算，不含任何 AI 判断。

用法:
    python3 tools/score_calculator.py scoring_data.json
    python3 tools/score_calculator.py scoring_data.json --output result.json
"""

import json
import sys
import argparse
from pathlib import Path


def calculate_dimension_score(dim_key, dim_data):
    """计算单个维度的得分 (0-100)。"""
    items = dim_data.get("items", [])
    if not items:
        return 0.0, 0, "无评分数据"

    total_score = 0.0
    total_max = 0.0
    details = []

    for i, item in enumerate(items):
        if dim_key == "technical_accuracy":
            score = item.get("score", 0)
            max_score = item.get("max_score", 10)
            total_score += score
            total_max += max_score
            details.append({
                "question": item.get("question_summary", f"Q{i+1}"),
                "score": f"{score}/{max_score}",
                "rating": item.get("rating", "N/A"),
                "evidence": item.get("evidence", "")
            })

        elif dim_key == "knowledge_depth":
            layers = item.get("layers_answered", 0)
            total_layers = item.get("followup_layers", 0)
            ratio = layers / total_layers if total_layers > 0 else 0
            normalized = ratio * 100
            total_score += normalized
            total_max += 100
            details.append({
                "question": item.get("question_summary", f"Q{i+1}"),
                "depth": f"{layers}/{total_layers} 层",
                "ratio": f"{ratio*100:.0f}%",
                "evidence": item.get("evidence", "")
            })

        elif dim_key == "system_design":
            checklist = item.get("checklist", {})
            total_checks = len(checklist)
            passed = sum(1 for v in checklist.values() if v)
            ratio = passed / total_checks if total_checks > 0 else 0
            normalized = ratio * 100
            total_score += normalized
            total_max += 100
            details.append({
                "question": item.get("question_summary", f"Q{i+1}"),
                "coverage": f"{passed}/{total_checks} 环节",
                "ratio": f"{ratio*100:.0f}%",
                "evidence": item.get("evidence", "")
            })

        elif dim_key == "coding":
            flags = ["approach_correct", "code_complete", "handles_edge_cases", "complexity_analyzed"]
            passed = sum(1 for f in flags if item.get(f, False))
            normalized = (passed / len(flags)) * 100
            total_score += normalized
            total_max += 100
            details.append({
                "question": item.get("question_summary", f"Q{i+1}"),
                "checks": f"{passed}/{len(flags)}",
                "evidence": item.get("evidence", "")
            })

        elif dim_key == "project_authenticity":
            flags = ["technical_details", "role_clarity", "challenges_described", "metrics_provided"]
            passed = sum(1 for f in flags if item.get(f, False))
            normalized = (passed / len(flags)) * 100
            total_score += normalized
            total_max += 100
            details.append({
                "project": item.get("project_name", f"Q{i+1}"),
                "checks": f"{passed}/{len(flags)}",
                "evidence": item.get("evidence", "")
            })

        elif dim_key == "communication":
            flags = ["uses_star_framework", "concise", "structured"]
            passed = sum(1 for f in flags if item.get(f, False))
            normalized = (passed / len(flags)) * 100
            total_score += normalized
            total_max += 100
            details.append({
                "question": item.get("question_summary", f"Q{i+1}"),
                "checks": f"{passed}/{len(flags)}",
                "evidence": item.get("evidence", "")
            })

        elif dim_key == "culture_fit":
            keywords_hit = item.get("value_keywords_hit", [])
            keywords_total = item.get("value_keywords_total", [])
            ratio = len(keywords_hit) / len(keywords_total) if keywords_total else 0
            normalized = ratio * 100
            total_score += normalized
            total_max += 100
            details.append({
                "question": item.get("question_summary", f"Q{i+1}"),
                "keywords": f"{len(keywords_hit)}/{len(keywords_total)}",
                "evidence": item.get("evidence", "")
            })

        elif dim_key == "audio_signals":
            score = item.get("score", 0)
            max_score = item.get("max_score", 10)
            normalized = (score / max_score) * 100 if max_score > 0 else 0
            total_score += normalized
            total_max += 100
            details.append({
                "metric": item.get("metric", f"Metric{i+1}"),
                "value": item.get("value", 0),
                "benchmark": item.get("benchmark", 0),
                "normalized": f"{normalized:.1f}/100"
            })

    dim_score = (total_score / total_max * 100) if total_max > 0 else 0.0
    return dim_score, len(items), details


def calculate_overall(scoring_data):
    """计算各维度得分和加权总分。"""
    dimensions = scoring_data.get("dimensions", {})
    results = {}
    weighted_total = 0.0
    total_weight = 0.0

    for dim_key, dim_data in dimensions.items():
        weight = dim_data.get("weight", 0)
        label = dim_data.get("label", dim_key)
        score, count, details = calculate_dimension_score(dim_key, dim_data)
        results[dim_key] = {
            "label": label,
            "weight": weight,
            "score": round(score, 1),
            "item_count": count,
            "details": details
        }
        weighted_total += score * weight
        total_weight += weight

    overall_score = (weighted_total / total_weight) if total_weight > 0 else 0.0

    sorted_dims = sorted(results.items(), key=lambda x: x[1]["score"])
    weakest = sorted_dims[:3]
    strongest = sorted_dims[-3:]

    return {
        "overall_score": round(overall_score, 1),
        "dimensions": results,
        "strongest": [{"dim": k, "label": v["label"], "score": v["score"]} for k, v in strongest],
        "weakest": [{"dim": k, "label": v["label"], "score": v["score"]} for k, v in weakest],
    }


def main():
    parser = argparse.ArgumentParser(description="面试评分加权计算器")
    parser.add_argument("input", help="评分数据 JSON 文件路径")
    parser.add_argument("--output", "-o", help="输出结果到 JSON 文件")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"错误: 文件不存在 {input_path}")
        sys.exit(1)

    with open(input_path, "r", encoding="utf-8") as f:
        scoring_data = json.load(f)

    result = calculate_overall(scoring_data)

    company = scoring_data.get("company", "未知")
    position = scoring_data.get("position", "未知")
    round_name = scoring_data.get("round", "未知")

    print(f"\n{'='*60}")
    print(f"  面试评分报告")
    print(f"  公司: {company} | 岗位: {position} | 轮次: {round_name}")
    print(f"{'='*60}")
    print(f"\n  总分: {result['overall_score']}/100\n")
    print(f"  {'维度':<20} {'权重':>6} {'得分':>8} {'题数':>6}")
    print(f"  {'-'*44}")
    for dim_key, dim in result["dimensions"].items():
        print(f"  {dim['label']:<20} {dim['weight']*100:>5.0f}% {dim['score']:>7.1f} {dim['item_count']:>6}")

    print(f"\n  优势维度:")
    for s in result["strongest"]:
        print(f"    ✅ {s['label']}: {s['score']}/100")

    print(f"\n  薄弱维度:")
    for w in result["weakest"]:
        print(f"    ⚠️  {w['label']}: {w['score']}/100")

    print(f"\n{'='*60}\n")

    if args.output:
        output_path = Path(args.output)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"结果已保存到 {output_path}")


if __name__ == "__main__":
    main()
