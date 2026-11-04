from types import SimpleNamespace
from unittest.mock import Mock

from livetranslate.translation import TranslationStep, Translator


def test_argos_step_tokenizes_and_removes_target_prefix():
    # No model download; checks integration contract with Argos packages/CTranslate2.
    step = TranslationStep.__new__(TranslationStep)
    tokenizer = Mock()
    tokenizer.encode.return_value = ['hello']
    tokenizer.decode.return_value = '<ru> Привет'
    step.package = SimpleNamespace(tokenizer=tokenizer, target_prefix='<ru>')
    step.runtime = Mock()
    step.runtime.translate_batch.return_value = [SimpleNamespace(hypotheses=[['привет']])]
    assert step.translate('Hello') == 'Привет'
    assert step.runtime.translate_batch.call_args.kwargs['target_prefix'] == [['<ru>']]


def test_translation_chain_passes_intermediate_text():
    translator = Translator.__new__(Translator)
    first, second = Mock(), Mock()
    first.translate.return_value = 'When?'
    second.translate.return_value = 'Когда?'
    translator.steps = [first, second]
    assert translator.translate('Wann?') == 'Когда?'
    second.translate.assert_called_once_with('When?')
