import re

def warnings(source, target):
    result = []
    if not target.strip():
        return ['空译文']
    if re.search(r'[\u3040-\u30ff]', target):
        result.append('残留日文假名')
    plain = re.sub(r'\{[^}]*\}|<[^>]*>', '', target).strip()
    if len(source.strip()) >= 8 and len(plain) < max(2, len(source.strip()) * .12):
        result.append('译文可能过短')
    if len(plain) > max(35, len(source) * 3.5):
        result.append('译文可能过长')
    if re.search(r'(.{1,12}?)(?:[，,、\s]*\1){3,}', plain):
        result.append('疑似机械重复；也可能是情绪表达，请核对')
    if re.search(r'([!?！？。，,])\1{3,}', plain):
        result.append('标点重复，请核对')
    if source.strip() == target.strip() and re.search(r'[\u3040-\u30ff]', source):
        result.append('原文未翻译')
    source_numbers = re.findall(r'\d+(?:[.,]\d+)*', source)
    target_numbers = re.findall(r'\d+(?:[.,]\d+)*', target)
    if source_numbers and source_numbers != target_numbers:
        result.append('数字可能变化，请核对')
    if '円' in source and not re.search(r'日元|日圓|円|yen|JPY', target, re.I):
        result.append('日元币种可能丢失，请核对')
    return result

def score(source, target):
    return len(warnings(source, target))

def safe_cleanup(text):
    # Do not delete repeated interjections: repetition can carry dramatic meaning.
    return text.replace('\x00', '').strip()
