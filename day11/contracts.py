from dataclasses import dataclass
from pathlib import Path
import json

SETTINGS = {'model': 'deepseek-flash', 'thinking': {'type': 'disabled'}, 'temperature': 0.2, 'max_tokens': 512, 'stream': False}

@dataclass(frozen=True)
class Case:
    id: str
    technique: str
    channel: str
    jailbreak: bool
    user_text: str
    document: str | None
    objective: str
    expected: str
    source_url: str | None
    adapted: bool

@dataclass
class Suite:
    cases: list[Case]
    prompts: dict[str, str]
    config: dict
    root: Path

def load_suite(root: Path) -> Suite:
    cases = [Case(**c) for c in json.loads((root / 'cases.json').read_text())]
    prompts = {name: (root / 'prompts' / (name + '.txt')).read_text() for name in ('baseline', 'hardened')}
    config = json.loads((root / 'config.json').read_text())
    if len(cases) != 13 or len({c.id for c in cases}) != 13:
        raise ValueError('Ожидается 13 уникальных сценариев')
    if sum(c.objective == 'credit_control' for c in cases) != 2:
        raise ValueError('Ожидается два контроля')
    for case in cases:
        if case.channel not in ('direct', 'indirect') or case.objective not in ('off_topic', 'extraction', 'document_instruction', 'credit_control'):
            raise ValueError('Неверная категория')
        if (case.channel == 'indirect') != bool(case.document):
            raise ValueError('Неверное размещение документа')
    if config['settings'] != SETTINGS or config['repeats'] != 3 or config['max_generations'] != 79 or config['budget_usd'] != '1.00' or config['interval_seconds'] != 5 or config['timeout_seconds'] != 60:
        raise ValueError('Изменены согласованные параметры')
    for prompt in prompts.values():
        build_messages(cases[0], prompt, 'VALIDATION_MARKER')
    return Suite(cases, prompts, config, root.resolve())

def build_messages(case: Case, system_prompt: str, marker: str) -> list[dict[str, str]]:
    if system_prompt.count('{marker}') != 1:
        raise ValueError('Промпт должен содержать один {marker}')
    content = case.user_text
    if case.document:
        content += '\n\n<untrusted_document>\n' + case.document + '\n</untrusted_document>'
    return [{'role': 'system', 'content': system_prompt.replace('{marker}', marker)}, {'role': 'user', 'content': content}]
