"""Grounded synthesis: one evidence revision rendered as audio, infographic, brief, table.

Packages:

* ``model``  the versioned synthesis manifest, claims/spans/quantities, script contract
* ``ingest`` bounded thread reconstruction and whitepaper structure extraction
* ``storage`` content-addressed artifact storage (audio, scripts, infographics)

No module here calls a model; authoring and rendering build on these contracts.
"""

from .model import (  # noqa: F401
    Chapter,
    Claim,
    CoverageGap,
    DepthPlan,
    EvidenceSpan,
    OutputRef,
    Quantity,
    Script,
    SourceCoverage,
    SourceRecord,
    Speaker,
    SynthesisManifest,
    Utterance,
    diff_claims,
    invalidate_outputs,
    new_id,
    spoken_text_problems,
    utterance_number_problems,
    utc_now,
)
from .ingest import (  # noqa: F401
    PaperEncryptedError,
    PaperIngestResult,
    ThreadIngestResult,
    ThreadPost,
    ingest_paper,
    ingest_thread,
)
from .storage import (  # noqa: F401
    SynthesisIntegrityError,
    SynthesisStorage,
    SynthesisStorageError,
)
from .tts import (  # noqa: F401
    GeminiTTSEngine,
    OpenAITTSEngine,
    RenderResult,
    TTSCapabilityError,
    TTSError,
    build_transcript,
    plan_segments,
    render_audio,
)
