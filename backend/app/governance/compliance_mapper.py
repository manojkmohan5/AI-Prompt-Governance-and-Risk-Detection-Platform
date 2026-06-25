"""
Maps governance flags to compliance framework requirements.
Returns tagged frameworks implicated by each flag for audit evidence.
"""
from typing import Dict, List

# flag → list of {framework, article, detail}
_MAP: Dict[str, List[Dict]] = {
    "PII_DETECTED": [
        {"framework": "GDPR",     "article": "Art. 5 & 25",   "detail": "Personal data must be protected by design and by default"},
        {"framework": "HIPAA",    "article": "§164.502",       "detail": "Restrictions on use and disclosure of PHI"},
        {"framework": "SOC 2",    "article": "CC6.1",          "detail": "Logical and physical access controls over personal data"},
    ],
    "SENSITIVE_DATA": [
        {"framework": "SOC 2",      "article": "CC6.1",   "detail": "Confidential information access controls"},
        {"framework": "ISO 42001",  "article": "6.1.2",   "detail": "AI risk assessment for sensitive data processing"},
        {"framework": "NIST AI RMF","article": "GOVERN 1.1","detail": "Organizational AI governance policies"},
        {"framework": "GDPR",       "article": "Art. 32",  "detail": "Security of processing — appropriate technical measures"},
    ],
    "PROMPT_INJECTION": [
        {"framework": "EU AI Act",   "article": "Art. 9",      "detail": "Risk management system for high-risk AI systems"},
        {"framework": "NIST AI RMF", "article": "GOVERN 1.1",  "detail": "AI risk management policies and procedures"},
        {"framework": "ISO 42001",   "article": "8.4",         "detail": "AI system security and adversarial attack controls"},
        {"framework": "SOC 2",       "article": "CC7.2",       "detail": "System monitoring for malicious activity"},
    ],
    "KNOWLEDGE_SHIELD": [
        {"framework": "SOC 2",       "article": "CC7.2",       "detail": "Continuous monitoring and anomaly detection"},
        {"framework": "ISO 42001",   "article": "8.4",         "detail": "AI intellectual property and data protection"},
        {"framework": "NIST AI RMF", "article": "MANAGE 2.2",  "detail": "AI incident response and recovery"},
        {"framework": "GDPR",        "article": "Art. 32",     "detail": "Security measures to prevent unauthorized disclosure"},
    ],
    "TOXICITY": [
        {"framework": "EU AI Act",   "article": "Art. 5",      "detail": "Prohibited AI practices — harmful or manipulative content"},
        {"framework": "NIST AI RMF", "article": "MAP 5.1",     "detail": "Identification and prevention of harmful AI outputs"},
        {"framework": "ISO 42001",   "article": "6.1.2",       "detail": "AI risk treatment for harmful content generation"},
    ],
    "USER_ANOMALY": [
        {"framework": "SOC 2",       "article": "CC7.3",       "detail": "Detection of anomalies and threats to system security"},
        {"framework": "NIST AI RMF", "article": "MEASURE 2.5", "detail": "Ongoing monitoring of AI risk indicators"},
        {"framework": "ISO 42001",   "article": "9.1",         "detail": "Monitoring and measurement of AI management system"},
    ],
    "ML_HIGH_RISK": [
        {"framework": "EU AI Act",   "article": "Art. 9",      "detail": "Risk management obligations for high-risk AI use cases"},
        {"framework": "NIST AI RMF", "article": "MAP 1.6",     "detail": "AI risk identification and prioritization"},
        {"framework": "ISO 42001",   "article": "6.1.2",       "detail": "AI risk treatment plans"},
    ],
    "IP_LEAK": [
        {"framework": "SOC 2",       "article": "CC7.2",       "detail": "Monitoring for unauthorised access to intellectual property"},
        {"framework": "ISO 42001",   "article": "8.4",         "detail": "AI intellectual property and data protection controls"},
        {"framework": "NIST AI RMF", "article": "MANAGE 2.2",  "detail": "AI incident response — confidential data exfiltration"},
        {"framework": "GDPR",        "article": "Art. 32",     "detail": "Security measures to prevent unauthorised disclosure"},
    ],
    "RESPONSE_SECRET_LEAK": [
        {"framework": "GDPR",        "article": "Art. 32", "detail": "Security measures to prevent personal data breaches"},
        {"framework": "SOC 2",       "article": "CC7.4",   "detail": "Security incident identification and response"},
        {"framework": "NIST AI RMF", "article": "MANAGE 2.4","detail": "AI output monitoring and corrective action"},
    ],
    "RESPONSE_INJECTION_ATTEMPT": [
        {"framework": "EU AI Act",   "article": "Art. 5",      "detail": "Prohibited AI output — adversarial instruction injection in responses"},
        {"framework": "NIST AI RMF", "article": "MAP 5.1",     "detail": "Identification and prevention of harmful AI outputs"},
        {"framework": "ISO 42001",   "article": "8.4",         "detail": "AI output validation and adversarial attack controls"},
    ],
    "EXCESSIVE_LENGTH": [
        {"framework": "ISO 42001",  "article": "8.4",  "detail": "AI input validation and boundary controls"},
        {"framework": "SOC 2",      "article": "CC6.6", "detail": "Boundary protection and input validation"},
    ],
}


def get_tags(flags: List[str]) -> List[str]:
    """Deduplicated list of 'Framework Article' strings for all given flags."""
    seen, tags = set(), []
    for flag in flags:
        for entry in _MAP.get(flag, []):
            key = f"{entry['framework']} {entry['article']}"
            if key not in seen:
                seen.add(key)
                tags.append(key)
    return tags


def get_detail(flags: List[str]) -> List[Dict]:
    """Full compliance detail objects for all given flags."""
    seen, details = set(), []
    for flag in flags:
        for entry in _MAP.get(flag, []):
            key = f"{entry['framework']} {entry['article']}"
            if key not in seen:
                seen.add(key)
                details.append({"flag": flag, **entry})
    return details
