# NLP Semantic Search Libraries Research

> **Date:** December 2024
> **Purpose:** Reference for implementing smart fuzzy/semantic search across projects
> **Key Requirement:** Zero user setup, auto-download models, low compute/space

---

## Executive Summary

For semantic search with minimal setup:
- **Python**: Use **FastEmbed** (Qdrant) - 22MB quantized ONNX, fastest
- **JavaScript**: Use **Transformers.js** (HuggingFace) - Works browser + Node + Bun
- **Rust**: Use **Candle** (HuggingFace) - Bleeding edge, fast

---

## Model Sizes Comparison

| Model | Size | Max Tokens | Quality | Use Case |
|-------|------|------------|---------|----------|
| **BGE-small-en-v1.5** | 63 MB | 512 | ⭐⭐⭐⭐ | Best balance |
| **GTE-small** | 70 MB | 512 | ⭐⭐⭐⭐ | Good alternative |
| **all-MiniLM-L6-v2** | 91 MB | 512 | ⭐⭐⭐⭐⭐ | Most popular |
| **e5-small-v2** | ~100 MB | 512 | ⭐⭐⭐⭐ | Multilingual |
| **BGE-micro** | ~22 MB | 512 | ⭐⭐⭐ | Smallest |

---

## Python Libraries

### FastEmbed (Qdrant) - RECOMMENDED
- **Size**: 22-63 MB (quantized ONNX models)
- **Speed**: Fastest (50% faster than PyTorch)
- **Auto-download**: Yes
- **Zero config**: Yes
- **Install**: `pip install fastembed`

```python
from fastembed import TextEmbedding

# Auto-downloads model on first use (~22MB for bge-small)
model = TextEmbedding("BAAI/bge-small-en-v1.5")
embeddings = list(model.embed(["search query", "document text"]))

# Compute similarity
import numpy as np
def cosine_similarity(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
```

### sentence-transformers
- **Size**: 91+ MB
- **Speed**: Good
- **Auto-download**: Yes
- **Install**: `pip install sentence-transformers`

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('all-MiniLM-L6-v2')  # Auto-downloads
embeddings = model.encode(['query', 'document'])
```

### txtai
- **Size**: Varies
- **Speed**: Good
- **Features**: All-in-one RAG, vector search built-in
- **Install**: `pip install txtai`

```python
from txtai.embeddings import Embeddings

embeddings = Embeddings({"path": "sentence-transformers/all-MiniLM-L6-v2"})
embeddings.index([("id1", "document text", None)])
results = embeddings.search("query", 10)
```

### spaCy
- **Size**: 12-500 MB depending on model
- **Best for**: NER, POS tagging, not semantic embeddings
- **Install**: `pip install spacy && python -m spacy download en_core_web_sm`

---

## JavaScript Libraries

### Transformers.js (HuggingFace) - RECOMMENDED
- **Size**: 30-100 MB (supports quantization: q8, q4)
- **Runtime**: Browser (WebGPU/WASM) + Node.js + Bun + Deno
- **Auto-download**: Yes (cached in IndexedDB for browser)
- **Speed**: Up to 100x faster with WebGPU vs WASM
- **Install**: `npm install @xenova/transformers`

```javascript
// ES Module (Node/Bun)
import { pipeline, env } from '@xenova/transformers';

// Optional: Use local cache
env.cacheDir = './.cache';

// Auto-downloads model on first use
const embedder = await pipeline('feature-extraction', 'Xenova/bge-small-en-v1.5');

// Get embeddings
const output = await embedder(['search query', 'document'], {
  pooling: 'mean',
  normalize: true
});

// Cosine similarity
function cosineSimilarity(a, b) {
  let dotProduct = 0, normA = 0, normB = 0;
  for (let i = 0; i < a.length; i++) {
    dotProduct += a[i] * b[i];
    normA += a[i] * a[i];
    normB += b[i] * b[i];
  }
  return dotProduct / (Math.sqrt(normA) * Math.sqrt(normB));
}
```

**Browser CDN Usage:**
```html
<script type="module">
  import { pipeline } from 'https://cdn.jsdelivr.net/npm/@xenova/transformers@2.17.0';

  const embedder = await pipeline('feature-extraction', 'Xenova/bge-small-en-v1.5');
  const embeddings = await embedder(['hello world'], { pooling: 'mean', normalize: true });
</script>
```

### Natural (Node.js only)
- **Size**: Tiny (no models)
- **Features**: Basic NLP, no semantic search
- **Install**: `npm install natural`

### Compromise (Browser + Node)
- **Size**: ~200KB
- **Features**: Fast NLP parsing, no semantic search
- **Install**: `npm install compromise`

---

## Rust Libraries

### Candle (HuggingFace) - Cutting Edge
- **Speed**: Fastest
- **Size**: Varies
- **Features**: Native Rust ML framework
- **Install**: Add to Cargo.toml

```rust
use candle_core::{Device, Tensor};
use candle_nn::VarBuilder;
use candle_transformers::models::bert::{BertModel, Config};
```

### rust-bert
- **Size**: 91+ MB
- **Auto-download**: Yes (downloads libtorch automatically)
- **Install**: Add to Cargo.toml

```rust
use rust_bert::pipelines::sentence_embeddings::{
    SentenceEmbeddingsBuilder, SentenceEmbeddingsModelType
};

let model = SentenceEmbeddingsBuilder::remote(
    SentenceEmbeddingsModelType::AllMiniLmL6V2
).create_model()?;

let embeddings = model.encode(&["query", "document"])?;
```

### ort (ONNX Runtime)
- **Speed**: Fast
- **Size**: Depends on model
- **Features**: Run any ONNX model

---

## Quantization Options

### What is Quantization?
Reduces model precision (float32 → int8/int4) to shrink size and speed up inference.

| Precision | Size Reduction | Speed | Accuracy Loss |
|-----------|----------------|-------|---------------|
| float32 | Baseline | Baseline | None |
| float16 | 50% | 1.5-2x | Minimal |
| int8 (q8) | 75% | 2-3x | Small |
| int4 (q4) | 87% | 3-4x | Moderate |

### Using Quantized Models

**Transformers.js:**
```javascript
// Specify quantization
const embedder = await pipeline('feature-extraction', 'Xenova/bge-small-en-v1.5', {
  quantized: true  // Uses q8 by default
});
```

**FastEmbed (Python):**
```python
# Already uses quantized ONNX by default
from fastembed import TextEmbedding
model = TextEmbedding("BAAI/bge-small-en-v1.5")  # Pre-quantized
```

---

## Architecture Patterns

### Pattern 1: Client-Side Only (Browser)
```
User Query → Transformers.js → Embeddings → Cosine Similarity → Results
                    ↓
           IndexedDB Cache (model persists)
```
- **Pros**: No server, works offline after first load
- **Cons**: 30-100MB initial download, slower on weak devices

### Pattern 2: Server-Side (Python/Node)
```
User Query → API → FastEmbed/Transformers.js → Embeddings → Search → Results
                           ↓
                   Model cached on server
```
- **Pros**: Fast, consistent, no client download
- **Cons**: Requires server, latency

### Pattern 3: Pre-computed Embeddings
```
Build Time: Documents → Embeddings → JSON file

Runtime: Query → Embed → Compare with pre-computed → Results
```
- **Pros**: Fastest search, small runtime overhead
- **Cons**: Need to rebuild when documents change

### Pattern 4: Hybrid
```
Server: Pre-compute document embeddings on startup
Client: Send query to server, get ranked results
```
- **Pros**: Best of both worlds
- **Cons**: More complex

---

## Performance Benchmarks

| Library | Embed 100 docs | Memory | Model Load |
|---------|----------------|--------|------------|
| FastEmbed | 0.3s | 150MB | 2s |
| sentence-transformers | 0.5s | 400MB | 3s |
| Transformers.js (Node) | 0.8s | 200MB | 4s |
| Transformers.js (Browser) | 1.5s | 150MB | 5s (first), 0.5s (cached) |

---

## Quick Start Examples

### Python + FastEmbed
```python
# requirements.txt
fastembed>=0.2.0
numpy>=1.24.0

# search.py
from fastembed import TextEmbedding
import numpy as np

class SemanticSearch:
    def __init__(self):
        self.model = TextEmbedding("BAAI/bge-small-en-v1.5")
        self.documents = []
        self.embeddings = []

    def index(self, documents):
        self.documents = documents
        self.embeddings = list(self.model.embed(documents))

    def search(self, query, top_k=5):
        query_emb = list(self.model.embed([query]))[0]
        scores = [np.dot(query_emb, doc_emb) for doc_emb in self.embeddings]
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        return [(self.documents[i], score) for i, score in ranked[:top_k]]

# Usage
search = SemanticSearch()
search.index(["data visualization expert", "SQL database admin", "frontend developer"])
results = search.search("charts and graphs")  # Finds "data visualization expert"
```

### JavaScript + Transformers.js
```javascript
// package.json: "@xenova/transformers": "^2.17.0"

import { pipeline } from '@xenova/transformers';

class SemanticSearch {
  constructor() {
    this.embedder = null;
    this.documents = [];
    this.embeddings = [];
  }

  async init() {
    this.embedder = await pipeline('feature-extraction', 'Xenova/bge-small-en-v1.5');
  }

  async index(documents) {
    this.documents = documents;
    const output = await this.embedder(documents, { pooling: 'mean', normalize: true });
    this.embeddings = output.tolist();
  }

  async search(query, topK = 5) {
    const queryEmb = (await this.embedder([query], { pooling: 'mean', normalize: true })).tolist()[0];

    const scores = this.embeddings.map((docEmb, i) => ({
      document: this.documents[i],
      score: this.cosineSimilarity(queryEmb, docEmb)
    }));

    return scores.sort((a, b) => b.score - a.score).slice(0, topK);
  }

  cosineSimilarity(a, b) {
    let dot = 0, normA = 0, normB = 0;
    for (let i = 0; i < a.length; i++) {
      dot += a[i] * b[i];
      normA += a[i] ** 2;
      normB += b[i] ** 2;
    }
    return dot / (Math.sqrt(normA) * Math.sqrt(normB));
  }
}

// Usage
const search = new SemanticSearch();
await search.init();
await search.index(['data visualization expert', 'SQL database admin', 'frontend developer']);
const results = await search.search('charts and graphs');
```

---

## References

- [FastEmbed GitHub](https://github.com/qdrant/fastembed)
- [Transformers.js GitHub](https://github.com/xenova/transformers.js)
- [sentence-transformers Docs](https://www.sbert.net/)
- [HuggingFace Model Hub](https://huggingface.co/models?pipeline_tag=feature-extraction)
- [MTEB Leaderboard](https://huggingface.co/spaces/mteb/leaderboard) - Embedding model benchmarks
- [Candle GitHub](https://github.com/huggingface/candle)
- [rust-bert GitHub](https://github.com/guillaume-be/rust-bert)

---

## Decision Matrix

| Requirement | FastEmbed | Transformers.js | sentence-transformers |
|-------------|-----------|-----------------|----------------------|
| Zero user setup | ✅ | ✅ | ✅ |
| Auto-download | ✅ | ✅ | ✅ |
| < 50MB model | ✅ (22MB) | ✅ (30MB q8) | ❌ (91MB) |
| Browser support | ❌ | ✅ | ❌ |
| Node/Bun support | ❌ | ✅ | ❌ |
| Python support | ✅ | ❌ | ✅ |
| Rust support | ❌ | ❌ | ❌ |
| Quantization | ✅ Built-in | ✅ Built-in | 🔶 Manual |
| Speed | ⚡⚡⚡ | ⚡⚡ | ⚡ |

---

## Hybrid Search: Transformers.js + Fuse.js

The Agent Transfer Viewer uses a **hybrid approach** combining:

1. **Transformers.js** (semantic embeddings) - Understands concepts like "dataviz" = "visualization"
2. **Fuse.js** (fuzzy string matching) - Handles typos like "grpahs" = "graphs"

### How It Works

```javascript
// Step 1: Correct typos before embedding
const correctedQuery = correctQueryTypos(query);  // "grpahs" → "graphs"

// Step 2: Get fuzzy scores (works even with heavy typos)
const fuzzyScores = getFuzzyScores(query);

// Step 3: Get semantic embeddings for corrected query
const queryEmbedding = await embedder([correctedQuery]);

// Step 4: Calculate semantic similarities
const semanticScores = agentEmbeddings.map(emb => cosineSimilarity(queryEmbedding, emb));

// Step 5: Combine scores (60% semantic + 40% fuzzy)
const hybridScore = (semanticScore * 0.6) + (fuzzyScore * 0.4);
```

### Fuse.js Configuration

```javascript
new Fuse(agentData, {
    keys: [
        { name: 'name', weight: 0.4 },
        { name: 'description', weight: 0.4 },
        { name: 'tools', weight: 0.2 }
    ],
    threshold: 0.4,           // 0=exact, 1=match anything
    distance: 100,            // How far to search for matches
    includeScore: true,       // Return match scores
    ignoreLocation: true,     // Don't penalize matches far from start
    minMatchCharLength: 2,    // Minimum chars to match
    findAllMatches: true      // Find all matches, not just first
});
```

### Benefits of Hybrid Approach

| Query | Semantic Only | Fuzzy Only | Hybrid |
|-------|---------------|------------|--------|
| "dataviz" | ✅ Finds visualization agents | ❌ No exact match | ✅ Works |
| "grpahs" | ❌ Misspelling breaks it | ✅ Finds "graphs" | ✅ Works |
| "fixusioinations" | ❌ | ✅ Finds "visualizations" | ✅ Works |
| "database queries" | ✅ Concept match | ❌ Partial match only | ✅ Works |

---

*Last updated: December 2024*
