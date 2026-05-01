import os
import re
import json
import configparser
import sys
from openai import OpenAI
from typing import List, Dict, Tuple

# 获取程序所在目录（兼容pyinstaller打包）
def get_app_dir():
    """获取应用程序所在目录"""
    if getattr(sys, 'frozen', False):
        # pyinstaller打包后的情况
        return os.path.dirname(os.path.abspath(sys.executable))
    else:
        # 正常运行情况
        return os.path.dirname(os.path.abspath(__file__))

APP_DIR = get_app_dir()

# 读取配置文件
config = configparser.ConfigParser()
config_path = os.path.join(APP_DIR, 'config.ini')

if not os.path.exists(config_path):
    print(f"错误：未找到配置文件 {config_path}")
    input("按任意键退出...")
    sys.exit(1)

config.read(config_path, encoding='utf-8')

# 初始化OpenAI客户端（兼容OpenAI格式的API）
try:
    client = OpenAI(
        api_key=config['API']['key'],
        base_url=config['API']['url']
    )
    model_name = config['API']['model']
except KeyError as e:
    print(f"错误：配置文件缺少必要的字段: {e}")
    input("按任意键退出...")
    sys.exit(1)

# 从配置文件读取批量大小和重试次数
try:
    BATCH_SIZE = int(config.get('Settings', 'batch_size', fallback=50))
    MAX_RETRIES = int(config.get('Settings', 'max_retries', fallback=3))
except ValueError:
    print("警告：配置文件中的 batch_size 或 max_retries 格式不正确，使用默认值")
    BATCH_SIZE = 50
    MAX_RETRIES = 3

def extract_messages(html_content: str) -> List[Dict]:
    """从HTML中提取聊天消息数据"""
    # 查找WEFLOW_DATA数组
    data_pattern = r'window\.WEFLOW_DATA\s*=\s*(\[.*?\]);'
    match = re.search(data_pattern, html_content, re.DOTALL)
    if not match:
        return []
    
    try:
        messages = json.loads(match.group(1))
        return messages
    except json.JSONDecodeError:
        return []

def extract_text_from_html(html_text: str) -> str:
    """从HTML消息内容中提取纯文本（不含时间）"""
    # 移除message-time标签及其内容（时间信息）
    text = re.sub(r'<div class="message-time">.*?</div>', '', html_text)
    # 移除HTML标签
    text = re.sub(r'<[^>]+>', '', text)
    # 移除语音转文字标记的前缀
    text = re.sub(r'^\[语音转文字-', '', text)
    # 移除首尾空白
    text = text.strip()
    return text

def batch_translate(texts: List[str]) -> List[str]:
    """批量翻译文本列表"""
    if not texts:
        return []
    
    total_count = len(texts)
    numbered_texts = "\n".join([f"{i+1}. {text}" for i, text in enumerate(texts)])
    
    system_prompt = """你是一个专业的翻译助手。请将用户输入的中文文本准确翻译成英文。

翻译规则：
1. 严格按照编号顺序输出，确保1到N的所有编号都存在
2. 每个编号占一行，格式为：编号. 翻译内容
3. 不要添加任何额外解释或说明
4. 如果原文为空或无法翻译，对应行输出空内容
5. 翻译结果要准确、完整、自然流畅
"""
    
    user_prompt = f"请翻译以下中文文本为英文，严格保持编号格式（共{total_count}条）：\n\n{numbered_texts}"
    
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,
            max_tokens=8000,
            response_format={"type": "text"}
        )
        
        result = response.choices[0].message.content.strip()
        
        # 使用字典映射确保编号对应
        translation_dict = {}
        for line in result.split('\n'):
            stripped_line = line.strip()
            if not stripped_line:
                continue
            match = re.match(r'^\s*(\d+)\.\s*(.*)', stripped_line)
            if match:
                line_num = int(match.group(1))
                translation_dict[line_num] = match.group(2).strip()
        
        # 按顺序构建结果列表
        translations = []
        for i in range(1, total_count + 1):
            translations.append(translation_dict.get(i, ''))
        
        return translations
    except Exception as e:
        print(f"  API调用失败: {str(e)}")
        return [''] * len(texts)

def apply_translation(messages, idx, translation):
    """应用翻译结果到消息"""
    msg = messages[idx]
    original_content = msg['b']
    
    # 在 message-text 标签后添加翻译（去掉[翻译]标记）
    translated_content = re.sub(
        r'(<div class="message-text">.*?</div>)',
        r'\1<div class="message-text" style="color: #6b7280; font-size: 12px; margin-top: 4px;">' + translation + '</div>',
        original_content,
        flags=re.DOTALL
    )
    
    msg['b'] = translated_content


def save_html(html_content, messages, output_file):
    """保存HTML文件"""
    new_data = json.dumps(messages, ensure_ascii=False, separators=(',', ':'))
    html_content = re.sub(
        r'window\.WEFLOW_DATA\s*=\s*\[.*?\];',
        f'window.WEFLOW_DATA = {new_data};',
        html_content,
        flags=re.DOTALL
    )
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_content)


def process_html_file(input_file: str, output_file: str = None):
    """处理HTML文件，批量翻译所有消息（包含重试机制）"""
    if output_file is None:
        output_file = input_file  # 原地替换
    
    # 读取HTML文件
    with open(input_file, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    # 提取消息
    messages = extract_messages(html_content)
    if not messages:
        print("未找到消息数据")
        return
    
    print(f"共找到 {len(messages)} 条消息")
    
    # 收集需要翻译的消息
    to_translate = []  # 存储 (索引, 原文) 元组
    
    for i, msg in enumerate(messages):
        msg_content = msg.get('b', '')
        
        # 跳过已翻译的消息
        if '[翻译]' in msg_content:
            continue
        
        # 提取纯文本（不含时间）
        text_content = extract_text_from_html(msg_content)
        
        # 跳过空消息、表情包或简单回复
        if not text_content:
            continue
        if text_content.startswith('[表情包') or text_content in ['好的', '没事的', '嗯嗯']:
            continue
        
        to_translate.append((i, text_content))
    
    print(f"待翻译消息: {len(to_translate)} 条")
    print(f"批量大小: {BATCH_SIZE}, 最大重试次数: {MAX_RETRIES}")
    
    if not to_translate:
        print("没有需要翻译的消息")
        return
    
    # 分批处理
    total_batches = (len(to_translate) + BATCH_SIZE - 1) // BATCH_SIZE
    failed_items = []  # 存储翻译失败的项目 (索引, 原文)
    
    for batch_idx in range(total_batches):
        start = batch_idx * BATCH_SIZE
        end = min(start + BATCH_SIZE, len(to_translate))
        batch = to_translate[start:end]
        
        print(f"\n处理批次 {batch_idx + 1}/{total_batches}（消息 {start + 1}-{end}）")
        
        # 提取文本列表
        indices = [item[0] for item in batch]
        texts = [item[1] for item in batch]
        
        # 批量翻译
        print(f"正在翻译 {len(texts)} 条消息...")
        translations = batch_translate(texts)
        
        # 应用翻译结果（确保严格对应）
        success = 0
        for i, (idx, translation) in enumerate(zip(indices, translations)):
            if translation:
                apply_translation(messages, idx, translation)
                success += 1
            else:
                failed_items.append((idx, texts[i]))  # 使用循环索引直接获取原文
        
        print(f"  成功: {success}, 失败: {len(texts) - success}")
        
        # 每批次完成后保存
        save_html(html_content, messages, output_file)
        print(f"批次 {batch_idx + 1} 已保存")
    
    # 重试失败的消息
    if failed_items:
        print(f"\n{"="*60}")
        print(f"开始重试 {len(failed_items)} 条失败的消息")
        print(f"{"="*60}")
        
        for retry_count in range(MAX_RETRIES):
            if not failed_items:
                break
            
            print(f"\n重试第 {retry_count + 1}/{MAX_RETRIES} 次")
            
            # 分批重试
            retry_batches = (len(failed_items) + BATCH_SIZE - 1) // BATCH_SIZE
            new_failed = []
            
            for batch_idx in range(retry_batches):
                start = batch_idx * BATCH_SIZE
                end = min(start + BATCH_SIZE, len(failed_items))
                batch = failed_items[start:end]
                
                indices = [item[0] for item in batch]
                texts = [item[1] for item in batch]
                
                print(f"  处理 {len(texts)} 条消息...")
                translations = batch_translate(texts)
                
                success = 0
                for i, (idx, translation) in enumerate(zip(indices, translations)):
                    if translation:
                        apply_translation(messages, idx, translation)
                        success += 1
                    else:
                        new_failed.append((idx, texts[i]))  # 使用循环索引直接获取原文
                
                print(f"    成功: {success}, 失败: {len(texts) - success}")
            
            # 保存重试结果
            save_html(html_content, messages, output_file)
            failed_items = new_failed
            
            if not failed_items:
                print("  所有失败消息重试成功！")
                break
        
        if failed_items:
            print(f"\n警告：仍有 {len(failed_items)} 条消息翻译失败")
            for idx, text in failed_items:
                print(f"  消息 {idx + 1}: {text[:50]}...")
    
    print("\n所有消息处理完成！")

if __name__ == "__main__":
    try:
        print(f"="*60)
        print(f"聊天记录翻译工具 v1.0")
        print(f"程序目录: {APP_DIR}")
        print(f"="*60)
        
        # 查找同级目录下的HTML文件
        html_files = [f for f in os.listdir(APP_DIR) if f.endswith('.html')]
        
        if not html_files:
            print("错误：未找到HTML文件")
            input("按任意键退出...")
            sys.exit(1)
        
        print(f"找到 {len(html_files)} 个HTML文件:")
        for i, file in enumerate(html_files, 1):
            print(f"  {i}. {file}")
        
        # 使用第一个HTML文件
        input_file = os.path.join(APP_DIR, html_files[0])
        print(f"\n开始处理文件: {html_files[0]}")
        
        process_html_file(input_file)
        
        print(f"\n" + "="*60)
        print("处理完成！")
        print(f"="*60)
        
    except Exception as e:
        print(f"\n程序运行出错: {str(e)}")
        import traceback
        traceback.print_exc()
    
    finally:
        input("\n按任意键退出...")