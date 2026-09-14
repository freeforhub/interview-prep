#!/usr/bin/env python3
"""Probability Model — 面试通过概率估算模型

基于贝叶斯估计，使用公开的面试通过率数据作为先验，
结合评分结果估算通过概率。

核心公式:
    P(通过|得分) = P(得分|通过) * P(通过) / P(得分)

不使用 AI 判断，纯统计模型。

用法:
    python3 tools/probability_model.py --score 72.5 --company "百度" --round "二面"
    python3 tools/probability_model.py --score-result result.json
    python3 tools/probability_model.py --score 68 --prior 0.25 --round-multiplier 0.8
"""

import json
import math
import sys
import argparse
from pathlib import Path


# 公开数据校准的模型参数（基于牛客网/知乎面经统计的粗略估计）
# 这些是先验分布参数，非 AI 判断

# 通过者的得分分布: N(mean=78, std=8)
PASS_MEAN = 78.0
PASS_STD = 8.0

# 未通过者的得分分布: N(mean=55, std=12)
FAIL_MEAN = 55.0
FAIL_STD = 12.0

# 各轮次通过率（校招，基于公开面经统计）
ROUND_PASS_RATES = {
    "笔试": 0.30,    # 笔试通过率约 20-40%
    "一面": 0.50,    # 一面通过率约 40-60%
    "二面": 0.40,    # 二面通过率约 30-50%
    "三面": 0.60,    # 三面通过率约 50-70%
    "HR面": 0.80,    # HR面通过率约 70-90%
    "终面": 0.70,    # 终面通过率约 60-80%
}

# 公司级别调整因子
COMPANY_TIERS = {
    "BAT": 0.15,      # 百度/阿里/腾讯 校招整体通过率约 10-20%
    "大厂": 0.20,     # 字节/美团/京东等
    "中厂": 0.30,     # 招银/CVTE/影石等
    "小厂": 0.40,     # 中小型公司
    "创业": 0.50,     # 创业公司
}

COMPANY_MAP = {
    "百度": "BAT", "阿里巴巴": "BAT", "腾讯": "BAT",
    "字节跳动": "大厂", "美团": "大厂", "京东": "大厂", "滴滴": "大厂",
    "网易": "大厂", "快手": "大厂", "小红书": "大厂", "华为": "大厂",
    "招银": "中厂", "招银网络": "中厂", "CVTE": "中厂", "视源": "中厂",
    "影石": "中厂", "Insta360": "中厂", "大疆": "大厂", "DJI": "大厂",
    "小米": "大厂", "OPPO": "大厂", "vivo": "大厂", "荣耀": "大厂",
}


def normal_pdf(x, mean, std):
    """正态分布概率密度函数。"""
    if std <= 0:
        return 0.0
    coeff = 1.0 / (std * math.sqrt(2 * math.pi))
    exponent = -((x - mean) ** 2) / (2 * std ** 2)
    return coeff * math.exp(exponent)


def estimate_probability(score, prior_pass_rate, round_multiplier=1.0):
    """贝叶斯估计通过概率。

    Args:
        score: 面试加权总分 (0-100)
        prior_pass_rate: 先验通过率 (0-1)
        round_multiplier: 轮次调整因子 (0-1)

    Returns:
        dict: 概率区间和详细信息
    """
    adjusted_prior = prior_pass_rate * round_multiplier
    adjusted_prior = max(0.01, min(0.95, adjusted_prior))

    p_score_given_pass = normal_pdf(score, PASS_MEAN, PASS_STD)
    p_score_given_fail = normal_pdf(score, FAIL_MEAN, FAIL_STD)

    p_score = p_score_given_pass * adjusted_prior + p_score_given_fail * (1 - adjusted_prior)
    if p_score < 1e-10:
        posterior = adjusted_prior
    else:
        posterior = (p_score_given_pass * adjusted_prior) / p_score

    posterior = max(0.01, min(0.99, posterior))

    margin = 0.10
    lower = max(0.0, posterior - margin)
    upper = min(1.0, posterior + margin)

    if posterior >= 0.75:
        confidence = "高"
        interpretation = "通过概率较高，表现优于多数通过者"
    elif posterior >= 0.55:
        confidence = "中"
        interpretation = "通过概率中等，处于通过/不通过的边界区"
    elif posterior >= 0.35:
        confidence = "中低"
        interpretation = "通过概率偏低，建议重点改进薄弱维度后争取后续轮次"
    else:
        confidence = "低"
        interpretation = "通过概率较低，需要大幅改进"

    score_vs_pass = (score - PASS_MEAN) / PASS_STD if PASS_STD > 0 else 0
    score_vs_fail = (score - FAIL_MEAN) / FAIL_STD if FAIL_STD > 0 else 0

    return {
        "probability": round(posterior * 100, 1),
        "probability_range": [round(lower * 100, 1), round(upper * 100, 1)],
        "confidence": confidence,
        "interpretation": interpretation,
        "prior_pass_rate": round(adjusted_prior * 100, 1),
        "score_distribution": {
            "pass_mean": PASS_MEAN,
            "pass_std": PASS_STD,
            "fail_mean": FAIL_MEAN,
            "fail_std": FAIL_STD,
            "z_score_vs_pass": round(score_vs_pass, 2),
            "z_score_vs_fail": round(score_vs_fail, 2),
        },
    }


def get_prior_pass_rate(company="", round_name=""):
    """根据公司名和轮次获取先验通过率。"""
    company_tier = "中厂"
    for name, tier in COMPANY_MAP.items():
        if name in company:
            company_tier = tier
            break

    base_rate = COMPANY_TIERS.get(company_tier, 0.30)

    round_rate = 0.50
    for key, rate in ROUND_PASS_RATES.items():
        if key in round_name:
            round_rate = rate
            break

    prior = base_rate * round_rate
    prior = max(0.02, min(0.90, prior))

    return prior, company_tier


def main():
    parser = argparse.ArgumentParser(description="面试通过概率估算模型")
    parser.add_argument("--score", type=float, help="面试加权总分 (0-100)")
    parser.add_argument("--company", default="", help="公司名")
    parser.add_argument("--round", default="", help="面试轮次")
    parser.add_argument("--prior", type=float, help="手动指定先验通过率 (0-1)")
    parser.add_argument("--round-multiplier", type=float, default=1.0,
                        help="轮次调整因子 (0-1)")
    parser.add_argument("--score-result", help="从 score_calculator 输出的 JSON 读取总分")
    parser.add_argument("--output", "-o", help="输出结果到 JSON 文件")
    args = parser.parse_args()

    if args.score_result:
        with open(args.score_result, "r", encoding="utf-8") as f:
            score_data = json.load(f)
        score = score_data.get("overall_score", 0)
        if not args.company:
            args.company = score_data.get("company", "")
    elif args.score is not None:
        score = args.score
    else:
        print("错误: 需要提供 --score 或 --score-result 参数")
        sys.exit(1)

    if args.prior is not None:
        prior = args.prior
        company_tier = "手动指定"
    else:
        prior, company_tier = get_prior_pass_rate(args.company, args.round)

    result = estimate_probability(score, prior, args.round_multiplier)
    result["company"] = args.company
    result["company_tier"] = company_tier
    result["round"] = args.round
    result["score"] = score

    print(f"\n{'='*55}")
    print(f"  面试通过概率估算")
    print(f"{'='*55}")
    print(f"\n  公司: {args.company or '未知'} ({company_tier})")
    print(f"  轮次: {args.round or '未知'}")
    print(f"  总分: {score}/100")
    print(f"  先验通过率: {result['prior_pass_rate']}%")
    print(f"\n  ┌─────────────────────────────────┐")
    print(f"  │  通过概率: {result['probability']}%")
    print(f"  │  概率区间: {result['probability_range'][0]}% - {result['probability_range'][1]}%")
    print(f"  │  置信度:   {result['confidence']}")
    print(f"  └─────────────────────────────────┘")
    print(f"\n  解读: {result['interpretation']}")
    print(f"\n  得分分布对比:")
    dist = result['score_distribution']
    print(f"    通过者均值: {dist['pass_mean']} (你的 Z-score: {dist['z_score_vs_pass']:+.2f})")
    print(f"    未通过均值: {dist['fail_mean']} (你的 Z-score: {dist['z_score_vs_fail']:+.2f})")
    print(f"\n  ⚠️  本模型基于公开面经数据的统计估计，仅供参考。")
    print(f"     实际通过率受面试官主观判断、岗位竞争度、HC 等因素影响。")
    print(f"\n{'='*55}\n")

    if args.output:
        output_path = Path(args.output)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"结果已保存到 {output_path}")


if __name__ == "__main__":
    main()
