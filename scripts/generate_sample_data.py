"""Write the synthetic sample documents to data/samples/."""

from pathlib import Path

from procureai.samples.generate import write_samples
from procureai.samples.packs import write_pack_samples

if __name__ == "__main__":
    out = Path(__file__).resolve().parent.parent / "data" / "samples"
    for p in write_samples(out):
        print("wrote", p.relative_to(out.parent.parent))
    for p in write_pack_samples(out / "platforms"):
        print("wrote", p.relative_to(out.parent.parent))
