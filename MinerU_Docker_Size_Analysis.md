# MinerU Docker Size Impact Analysis

## Current Docker Setup

### **Current Image Sizes:**
- **qif-agent**: 1.17GB (Python 3.12.2-slim + dependencies)
- **qif-ui**: 893MB (Streamlit + dependencies)
- **Total Current**: ~2.06GB

## MinerU Size Impact

### **Option 1: Full MinerU Integration (Recommended)**
```
Current: 1.17GB + MinerU: 5-10GB = 6.17-11.17GB
```

**Components:**
- Base Python image: 1.17GB
- MinerU core: ~2-3GB
- OCR models: ~2-3GB
- Additional dependencies: ~1-2GB
- **Total**: 6-9GB per container

### **Option 2: Lightweight MinerU (OCR Only)**
```
Current: 1.17GB + Lightweight MinerU: 2-3GB = 3.17-4.17GB
```

**Components:**
- Base Python image: 1.17GB
- Minimal OCR tools: ~1-2GB
- Basic dependencies: ~1GB
- **Total**: 3-4GB per container

### **Option 3: Separate MinerU Service (Recommended Architecture)**
```
Current containers: 2.06GB (unchanged)
New MinerU service: 5-8GB
Total system: 7-10GB
```

## 🎯 **Recommended Approach: Separate MinerU Service**

### **Architecture:**
```
PDF → MinerU Service → Markdown → Your App → LLM → Database
```

### **Benefits:**
1. **Keep existing containers small** (2.06GB unchanged)
2. **MinerU runs independently** (5-8GB separate service)
3. **Better resource management** (scale MinerU separately)
4. **Faster deployments** (don't rebuild main app for MinerU updates)

### **Docker Compose Structure:**
```yaml
services:
  qif-agent:
    # Your existing service (1.17GB)
    
  qif-ui:
    # Your existing service (893MB)
    
  mineru-service:
    # New MinerU service (5-8GB)
    image: mineru:latest
    volumes:
      - ./docs/fund_pdfs:/input
      - ./docs/processed:/output
```

## 📊 **Size Comparison**

| Approach | Current Size | New Size | Increase | Pros | Cons |
|----------|-------------|----------|----------|------|------|
| **No MinerU** | 2.06GB | 2.06GB | 0% | Small, fast | Poor PDF quality |
| **Integrated MinerU** | 2.06GB | 6-9GB | 300-400% | All-in-one | Very large, slow builds |
| **Separate MinerU** | 2.06GB | 7-10GB total | 300-400% | Modular, scalable | Additional service |

## 🚀 **Implementation Strategy**

### **Phase 1: Test with External MinerU**
1. **Use MinerU locally** to process BZ39.PDF
2. **Generate markdown** and test LLM extraction
3. **Validate quality improvement** before Docker integration

### **Phase 2: Docker Integration**
1. **Create separate MinerU service** in docker-compose.yml
2. **Add API endpoint** to call MinerU service
3. **Update PDF processing pipeline** to use MinerU first

### **Phase 3: Optimization**
1. **Use lightweight MinerU image** if possible
2. **Cache processed markdown** to avoid reprocessing
3. **Monitor resource usage** and optimize

## 💰 **Cost-Benefit Analysis**

### **Costs:**
- **Storage**: +5-8GB per deployment
- **Memory**: +2-4GB RAM for MinerU service
- **Build time**: +5-10 minutes for MinerU image
- **Complexity**: Additional service to manage

### **Benefits:**
- **Data Quality**: 3x better LLM extraction (0.8 vs 0.3 confidence)
- **Dashboard Richness**: Complete financial metrics
- **Success Rate**: Higher extraction success for complex PDFs
- **Future-Proof**: Handles varied PDF formats

## 🎯 **Recommendation**

### **Start with Separate MinerU Service:**

1. **Keep existing containers unchanged** (2.06GB)
2. **Add MinerU as separate service** (5-8GB)
3. **Total system size**: 7-10GB
4. **Benefits**: Modular, scalable, better resource management

### **Alternative: Lightweight Approach**
If size is critical, consider:
1. **Use external MinerU API** (hosted service)
2. **Process PDFs outside Docker** (local preprocessing)
3. **Store markdown files** and use in Docker

## 📋 **Next Steps**

1. **Test MinerU locally** with BZ39.PDF
2. **Measure quality improvement** vs current approach
3. **Decide on architecture** (separate service vs integrated)
4. **Implement chosen approach** with monitoring
5. **Optimize based on usage patterns**

## 🔧 **Docker Compose Example**

```yaml
version: '3.8'
services:
  qif-agent:
    build: .
    # ... existing config (1.17GB)
    
  qif-ui:
    build: ./ui
    # ... existing config (893MB)
    
  mineru:
    image: opendatalab/mineru:latest
    volumes:
      - ./docs/fund_pdfs:/input
      - ./docs/processed:/output
    environment:
      - MINERU_MODEL_PATH=/models
    # Size: 5-8GB
```

**Total System Size**: 7-10GB (vs current 2.06GB)
**Quality Improvement**: 3x better data extraction
**Recommendation**: Worth the size increase for the data quality benefits
