"""Offline Argos models. Network downloads only via explicit setup command."""
PAIRS = [("de", "en"), ("en", "ru")]


def install_models(status=print):
    import argostranslate.package as package
    package.update_package_index()
    available = package.get_available_packages()
    installed = {(p.from_code, p.to_code) for p in package.get_installed_packages()}
    for source, target in PAIRS:
        if (source, target) in installed:
            continue
        match = next((p for p in available if p.from_code == source and p.to_code == target), None)
        if match is None:
            raise RuntimeError(f"Нет пакета Argos {source} → {target}")
        status(f"Загрузка Argos {source} → {target}…")
        package.install_from_path(match.download())


class TranslationStep:
    """Run one Argos package with CTranslate2, treating a short VAD chunk as one sentence.

    No external sentence-boundary models or conversation caches are needed.
    """
    def __init__(self, package):
        import ctranslate2
        self.package = package
        self.runtime = ctranslate2.Translator(
            str(package.package_path / "model"), device="cpu", compute_type="int8",
            inter_threads=1, intra_threads=2,
        )

    def translate(self, text):
        package = self.package
        prefix = package.target_prefix
        result = self.runtime.translate_batch(
            [package.tokenizer.encode(text)], beam_size=2, replace_unknowns=True,
            target_prefix=[[prefix]] if prefix else None,
        )[0]
        value = package.tokenizer.decode(result.hypotheses[0])
        if prefix and value.startswith(prefix):
            value = value[len(prefix):].lstrip()
        return value


class Translator:
    def __init__(self):
        from argostranslate.package import get_installed_packages
        packages = {(p.from_code, p.to_code): p for p in get_installed_packages()}
        if not all(pair in packages for pair in PAIRS):
            raise RuntimeError("Нет моделей перевода. Выполните: python -m livetranslate --setup-models")
        self.steps = [TranslationStep(packages[pair]) for pair in PAIRS]

    def translate(self, text):
        for step in self.steps:
            text = step.translate(text)
        return text
