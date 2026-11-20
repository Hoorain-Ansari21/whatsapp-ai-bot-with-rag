"""Websites the extraction agent crawls to build the knowledge base.

Each Source is one website. The crawler always fetches the `seeds`, then
follows links on the same site up to `max_depth` clicks away, as long as the
link path starts with one of `allow_paths` (empty list = whole site).

To add a site, add a Source below and rebuild with:
    python build_knowledge_base.py --force
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Source:
    name: str
    category: str
    seeds: list[str]
    allow_paths: list[str] = field(default_factory=list)
    max_depth: int | None = None  # None = use the global default (2)
    max_pages: int | None = None  # None = use the global default (300)


# Categories: universities, policies, guidance, local_scholarships,
# university_aid, abroad_scholarships
SOURCES: list[Source] = [
    # ---------------- HEC: universities, policies, scholarships, attestation
    Source(
        name="HEC Pakistan",
        category="hec",
        seeds=[
            "https://www.hec.gov.pk/english/universities/pages/recognised.aspx",
            "https://www.hec.gov.pk/english/universities/Pages/DAIs/HEC-recognized-Campuses.aspx",
            "https://www.hec.gov.pk/english/universities/Pages/AJK/Illegal-DAIs.aspx",
            "https://www.hec.gov.pk/english/policies/Pages/UGEP.aspx",
            "https://www.hec.gov.pk/english/services/faculty/Plagiarism/Documents/Graduate-Education-Policy.pdf",
            "https://www.hec.gov.pk/english/services/students/DAS/Pages/Degree-Attestation.aspx",
            "https://www.hec.gov.pk/english/scholarshipsgrants/Pages/NationalScholarships.aspx",
            "https://www.hec.gov.pk/english/scholarshipsgrants/Pages/internationalScholarships.aspx",
            "https://www.hec.gov.pk/english/scholarshipsgrants/lao/Pages/default.aspx",
            "https://www.hec.gov.pk/english/scholarshipsgrants/lao/CGSP/Pages/default.aspx",
            "https://www.hec.gov.pk/english/scholarshipsgrants/lao/SHSP/Pages/default.aspx",
            "https://www.hec.gov.pk/english/scholarshipsgrants/lao/SHSP/Pages/FAQs.aspx",
            "https://www.hec.gov.pk/english/scholarshipsgrants/lao/cwgs/Pages/default.aspx",
            "https://www.hec.gov.pk/english/scholarshipsgrants/lao/cwgs/Pages/FAQs.aspx",
        ],
        allow_paths=[
            "/english/universities",
            "/english/scholarshipsgrants",
            "/english/policies",
            "/english/services/students",
        ],
        max_pages=600,  # HEC is the main source, so it gets a bigger budget
    ),
    # ---------------- Provincial endowment funds
    Source(
        name="PEEF (Punjab Educational Endowment Fund)",
        category="local_scholarships",
        seeds=["https://peef.org.pk/", "https://hed.punjab.gov.pk/peef"],
    ),
    Source(
        name="SEEF (Sindh Educational Endowment Fund)",
        category="local_scholarships",
        seeds=["https://seef.sindh.gov.pk/", "https://seef.sindh.gov.pk/about-us"],
    ),
    Source(
        name="KP Chief Minister Educational Endowment Fund",
        category="local_scholarships",
        seeds=["https://hed.gkp.pk/content/chief-minister-educational-endowment-fund-cmeef"],
        allow_paths=["/content"],
        max_depth=1,
    ),
    # ---------------- University fees and financial aid
    Source(
        name="LUMS Financial Aid",
        category="university_aid",
        seeds=["https://financial-aid.lums.edu.pk/", "https://nop.lums.edu.pk/"],
    ),
    Source(
        name="NUST Admissions & Financial Aid",
        category="university_aid",
        seeds=["https://nust.edu.pk/admissions/", "https://nust.edu.pk/admissions/scholarships/"],
        allow_paths=["/admissions"],
    ),
    Source(
        name="IBA Karachi Financial Assistance",
        category="university_aid",
        seeds=["https://www.iba.edu.pk/"],
        allow_paths=["/financialassistance", "/admissions", "/fee"],
    ),
    # ---------------- Scholarships abroad
    Source(
        name="Fulbright Pakistan (USEFP)",
        category="abroad_scholarships",
        seeds=["https://www.usefp.org/"],
    ),
    Source(
        name="Chevening Pakistan",
        category="abroad_scholarships",
        seeds=["https://chevening.org/scholarship/pakistan"],
        allow_paths=["/scholarship"],
    ),
    Source(
        name="Commonwealth Scholarships (UK)",
        category="abroad_scholarships",
        seeds=["https://cscuk.fcdo.gov.uk/scholarships/"],
        allow_paths=["/scholarships"],
    ),
    Source(
        name="DAAD Pakistan",
        category="abroad_scholarships",
        seeds=["https://www.daad.pk/en/find-funding/daad-scholarship-programmes-for-pakistan/"],
        allow_paths=["/en/"],
    ),
    Source(
        name="MEXT Japan (Embassy of Japan in Pakistan)",
        category="abroad_scholarships",
        seeds=["https://www.pk.emb-japan.go.jp/itpr_en/education.html"],
        allow_paths=["/itpr_en/"],
    ),
    Source(
        name="Erasmus Mundus",
        category="abroad_scholarships",
        seeds=["https://www.eacea.ec.europa.eu/scholarships/erasmus-mundus-catalogue_en"],
        allow_paths=["/scholarships"],
    ),
    Source(
        name="Türkiye Bursları",
        category="abroad_scholarships",
        seeds=["https://turkiyeburslari.gov.tr/"],
    ),
]
