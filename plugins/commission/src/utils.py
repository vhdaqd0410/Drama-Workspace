"""共享工具函数 —— 供 features.py 与 generate_commission.py 复用"""
import re


def clean(text):
    """清理单元格文本：去空、统一空白"""
    if text is None:
        return ''
    s = str(text).replace('\xa0', ' ').replace('\n', '').replace('\r', '')
    return re.sub(r'\s+', ' ', s).strip()


def parse_episode_ranges(text):
    """解析集数范围字符串，返回 (集号列表, 数量)。支持：1-3,5,7-10 等多种格式"""
    if not text:
        return [], 0
    text = clean(text)
    if not text:
        return [], 0
    # 多分隔符统一：逗号/分号/加号/空格 -> 逗号
    text = re.sub(r'[；;，,。+、\s]+', ',', text).strip(',')
    episodes = []
    for part in re.split(r',', text):
        part = part.strip()
        if not part:
            continue
        m = re.match(r'(\d+)\s*[-–—]\s*(\d+)', part)
        if m:
            s, e = int(m.group(1)), int(m.group(2))
            episodes.extend(range(min(s, e), max(s, e) + 1))
        else:
            m = re.match(r'(\d+)', part)
            if m:
                episodes.append(int(m.group(1)))
    result = sorted(set(episodes))
    return result, len(result)


def parse_overtime_episodes(text):
    """解析超时/集数标注，返回 set of int。支持：4,5,10-12 或 4 5 10"""
    if not text:
        return set()
    eps, _ = parse_episode_ranges(text)
    return set(eps)


def merge_episode_ranges(episodes):
    """将离散集号合并为 (start,end) 区间列表"""
    episodes = sorted(set(episodes))
    if not episodes:
        return []
    result, start, end = [], episodes[0], episodes[0]
    for episode in episodes[1:]:
        if episode == end + 1:
            end = episode
        else:
            result.append((start, end))
            start = end = episode
    result.append((start, end))
    return result
