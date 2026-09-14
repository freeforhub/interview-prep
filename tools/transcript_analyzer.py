#!/usr/bin/env python3
"""Transcript Analyzer — 转写文本分析器

分析面试转写文本的客观音频/语言信号：
- 迟疑词频率
- 语速变化
- 停顿/沉默占比
- 技术术语密度

用法:
    python3 tools/transcript_analyzer.py transcript.txt
    python3 tools/transcript_analyzer.py transcript.txt --output signals.json
    python3 tools/transcript_analyzer.py transcript.json --format whisper
"""

import json
import re
import sys
import argparse
from pathlib import Path

HESITATION_WORDS = [
    "嗯", "啊", "额", "呃", "那个", "就是", "然后", "这个",
    "怎么说呢", "怎么说", "其实吧", "说白了", "反正",
    "emmm", "uh", "um", "uhm", "like", "you know",
    "so yeah", "I mean", "sort of", "kind of",
]

TECH_TERM_PATTERNS = [
    r'\b(API|HTTP|HTTPS|TCP|UDP|DNS|CDN|REST|gRPC|GraphQL)\b',
    r'\b(Docker|Kubernetes|K8s|Jenkins|Nginx|Redis|MySQL|Kafka|MongoDB)\b',
    r'\b(HashMap|ConcurrentHashMap|JVM|GC|G1|CMS|volatile|synchronized)\b',
    r'\b(RESTful|CRUD|ACID|CAP|BASE|MVCC|B\+树|B树|红黑树)\b',
    r'\b(Redis|RDB|AOF|LRU|LFU|MQ|RPC|SOA|微服务|分布式|高可用)\b',
    r'\b(Linux|epoll|select|poll|socket|fd|进程|线程|协程|锁|信号量)\b',
    r'\b(算法|复杂度|O\(|排序|二叉树|链表|栈|队列|哈希表|动态规划)\b',
    r'\b(C\+\+|C\+\+11|C\+\+14|C\+\+17|C\+\+20|STL|RAII|move|智能指针)\b',
    r'\b(Go|Golang|goroutine|channel|GMP|defer|interface)\b',
    r'\b(Java|Spring|SpringBoot|MyBatis|Maven|Gradle|JIT|字节码)\b',
    r'\b(Python|pip|venv|asyncio|GIL|decorator|generator|yield)\b',
    r'\b(AI|LLM|RAG|Agent|LangChain|LangGraph|Prompt|Embedding|向量|chunk)\b',
    r'\b(Git|GitHub|GitLab|CI|CD|DevOps|SRE|SLO|SLI|OnCall)\b',
    r'\b(虚拟机|KVM|Xen|容器|namespace|cgroup|overlay|bridge|NAT)\b',
    r'\b(OSPF|BGP|VLAN|STP|RSTP|MSTP|MAC|ARP|ICMP|BGP|AS|CIDR|子网)\b',
]

TECH_TERM_REGEX = re.compile('|'.join(TECH_TERM_PATTERNS), re.IGNORECASE)

CHINESE_CHAR_REGEX = re.compile(r'[\u4e00-\u9fff]')
CHINESE_SENTENCE_REGEX = re.compile(r'[^。！？.!?]+[。！？.!?]')
WORD_SEGMENT_REGEX = re.compile(r'[\s,，;；、]+')


def count_chinese_chars(text):
    """统计中文字符数。"""
    return len(CHINESE_CHAR_REGEX.findall(text))


def count_words(text):
    """估算文本词数（中文字符数 + 英文单词数）。"""
    chinese_chars = count_chinese_chars(text)
    english_words = len(re.findall(r'[a-zA-Z]+', text))
    return chinese_chars + english_words


def analyze_hesitation(text):
    """分析迟疑词频率（次/百字）。"""
    word_count = max(count_words(text), 1)
    total_hesitations = 0
    detail = {}

    for word in HESITATION_WORDS:
        count = text.lower().count(word.lower())
        if count > 0:
            detail[word] = count
            total_hesitations += count

    frequency = total_hesitations / word_count * 100

    if frequency <= 1.5:
        score = 10
    elif frequency <= 3.0:
        score = 8
    elif frequency <= 5.0:
        score = 6
    elif frequency <= 8.0:
        score = 4
    else:
        score = 2

    return {
        "frequency": round(frequency, 2),
        "total_hesitations": total_hesitations,
        "detail": detail,
        "score": score,
        "max_score": 10,
    }


def analyze_speech_rate(text, segments=None):
    """分析语速变化（分段对比前半段 vs 后半段）。"""
    if segments:
        midpoint = len(segments) // 2
        first_half = " ".join(segments[:midpoint])
        second_half = " ".join(segments[midpoint:])
    else:
        sentences = CHINESE_SENTENCE_REGEX.findall(text)
        if len(sentences) < 2:
            return {"variance": 0.0, "score": 10, "max_score": 10}
        midpoint = len(sentences) // 2
        first_half = "".join(sentences[:midpoint])
        second_half = "".join(sentences[midpoint:])

    words_first = max(count_words(first_half), 1)
    words_second = max(count_words(second_half), 1)

    if segments:
        time_first = sum(s.get("end", 0) - s.get("start", 0) for s in segments[:midpoint])
        time_second = sum(s.get("end", 0) - s.get("start", 0) for s in segments[midpoint:])
        rate_first = words_first / max(time_first, 0.1)
        rate_second = words_second / max(time_second, 0.1)
    else:
        rate_first = words_first
        rate_second = words_second

    if rate_first > 0:
        variance = abs(rate_second - rate_first) / rate_first * 100
    else:
        variance = 0.0

    if variance <= 10:
        score = 10
    elif variance <= 20:
        score = 8
    elif variance <= 35:
        score = 6
    elif variance <= 50:
        score = 4
    else:
        score = 2

    return {
        "rate_first_half": round(rate_first, 2),
        "rate_second_half": round(rate_second, 2),
        "variance": round(variance, 2),
        "score": score,
        "max_score": 10,
    }


def analyze_silence(segments):
    """分析停顿/沉默占比（需要 Whisper 时间戳）。"""
    if not segments:
        return {"silence_ratio": 0.0, "score": 10, "max_score": 10}

    total_time = segments[-1].get("end", 0) - segments[0].get("start", 0)
    if total_time <= 0:
        return {"silence_ratio": 0.0, "score": 10, "max_score": 10}

    speech_time = 0
    for seg in segments:
        speech_time += seg.get("end", 0) - seg.get("start", 0)

    silence_time = total_time - speech_time
    silence_ratio = silence_time / total_time * 100

    if silence_ratio <= 5:
        score = 10
    elif silence_ratio <= 10:
        score = 8
    elif silence_ratio <= 20:
        score = 6
    elif silence_ratio <= 35:
        score = 4
    else:
        score = 2

    return {
        "silence_ratio": round(silence_ratio, 2),
        "total_time": round(total_time, 1),
        "speech_time": round(speech_time, 1),
        "silence_time": round(silence_time, 1),
        "score": score,
        "max_score": 10,
    }


def analyze_tech_term_density(text):
    """分析技术术语密度（术语数/百字）。"""
    word_count = max(count_words(text), 1)
    matches = TECH_TERM_REGEX.findall(text)
    density = len(matches) / word_count * 100

    if density >= 5:
        score = 10
    elif density >= 3:
        score = 8
    elif density >= 1.5:
        score = 6
    elif density >= 0.5:
        score = 4
    else:
        score = 2

    return {
        "density": round(density, 2),
        "total_tech_terms": len(matches),
        "score": score,
        "max_score": 10,
    }


def analyze_transcript(text, whisper_data=None):
    """综合分析转写文本。"""
    segments = None
    if whisper_data and "segments" in whisper_data:
        segments = whisper_data["segments"]
    elif isinstance(text, list):
        segments = text

    result = {
        "hesitation": analyze_hesitation(text if isinstance(text, str) else " ".join(s.get("text", "") for s in segments)),
        "speech_rate": analyze_speech_rate(
            text if isinstance(text, str) else "",
            segments
        ),
        "silence": analyze_silence(segments) if segments else {
            "silence_ratio": 0.0, "score": 0, "max_score": 10,
            "note": "无时间戳数据，跳过停顿分析"
        },
        "tech_term_density": analyze_tech_term_density(
            text if isinstance(text, str) else " ".join(s.get("text", "") for s in segments)
        ),
    }

    scores = [r["score"] for r in result.values() if "score" in r]
    result["overall_audio_score"] = round(sum(scores) / max(len(scores), 1), 1)

    return result


def main():
    parser = argparse.ArgumentParser(description="面试转写文本分析器")
    parser.add_argument("input", help="转写文本文件 (txt 或 json)")
    parser.add_argument("--format", choices=["text", "whisper"], default="auto",
                        help="输入格式：text=纯文本, whisper=Whisper JSON")
    parser.add_argument("--output", "-o", help="输出结果到 JSON 文件")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"错误: 文件不存在 {input_path}")
        sys.exit(1)

    fmt = args.format
    if fmt == "auto":
        fmt = "whisper" if input_path.suffix == ".json" else "text"

    with open(input_path, "r", encoding="utf-8") as f:
        raw = f.read()

    whisper_data = None
    text = raw

    if fmt == "whisper":
        whisper_data = json.loads(raw)
        text = whisper_data.get("text", "")
        if not text and "segments" in whisper_data:
            text = " ".join(s.get("text", "") for s in whisper_data["segments"])

    result = analyze_transcript(text, whisper_data)

    print(f"\n{'='*50}")
    print(f"  音频信号分析报告")
    print(f"{'='*50}")

    h = result["hesitation"]
    print(f"\n  迟疑词频率: {h['frequency']}/百字  ({h['total_hesitations']} 次)")
    if h.get("detail"):
        top = sorted(h["detail"].items(), key=lambda x: x[1], reverse=True)[:5]
        print(f"    高频: {', '.join(f'{w}({c}次)' for w, c in top)}")
    print(f"    得分: {h['score']}/10")

    r = result["speech_rate"]
    print(f"\n  语速变化: {r['variance']}%")
    print(f"    前半段: {r['rate_first_half']} | 后半段: {r['rate_second_half']}")
    print(f"    得分: {r['score']}/10")

    s = result["silence"]
    if s.get("silence_ratio", 0) > 0 or "total_time" in s:
        print(f"\n  停顿占比: {s.get('silence_ratio', 0)}%")
        if "total_time" in s:
            print(f"    总时长: {s['total_time']}s | 发言: {s['speech_time']}s | 沉默: {s['silence_time']}s")
        print(f"    得分: {s.get('score', 0)}/10")
    else:
        print(f"\n  停顿分析: {s.get('note', '无数据')}")

    t = result["tech_term_density"]
    print(f"\n  技术术语密度: {t['density']}/百字 ({t['total_tech_terms']} 个)")
    print(f"    得分: {t['score']}/10")

    print(f"\n  音频信号总分: {result['overall_audio_score']}/10")
    print(f"\n{'='*50}\n")

    if args.output:
        output_path = Path(args.output)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"结果已保存到 {output_path}")


if __name__ == "__main__":
    main()
