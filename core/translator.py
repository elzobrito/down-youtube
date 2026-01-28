class Translator:
    SUPPORTED_LANGUAGES = {
        "pt": "Portuguese",
        "en": "English",
        "es": "Spanish",
        "fr": "French",
        "de": "German",
        "it": "Italian",
        "ja": "Japanese",
        "ko": "Korean",
        "zh-CN": "Chinese (Simplified)",
        "ru": "Russian",
    }

    def __init__(self, source="auto", target="pt"):
        self.source = source
        self.target = target
        module = importlib.import_module("deep_translator")
        GoogleTranslator = getattr(module, "GoogleTranslator")
        self.translator = GoogleTranslator(source=source, target=target)

    def translate(self, text):
        if not text:
            return ""
        chunks = self._split_text(text, 5000)
        translated_chunks = []
        for chunk in chunks:
            translated_chunks.append(self.translator.translate(chunk))
        return "\n".join(translated_chunks)

    def translate_segments(self, segments):
        if not segments:
            return []
        translated_segments = []
        for seg in segments:
            translated_text = self.translator.translate(seg.get("text", ""))
            translated_segments.append(
                {
                    "start": seg.get("start"),
                    "end": seg.get("end"),
                    "text": translated_text,
                }
            )
        return translated_segments

    def _split_text(self, text, max_length):
        chunks = []
        current_chunk = ""
        for paragraph in text.split("\n"):
            if len(current_chunk) + len(paragraph) < max_length:
                current_chunk += paragraph + "\n"
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = paragraph + "\n"
        if current_chunk:
            chunks.append(current_chunk)
        return chunks
import importlib
