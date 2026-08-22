"""Forty SEBI reference strings, in the formats the corpus actually uses.

The brief requires the citation regex be tested against a fixture of 40 real
reference strings. These follow the published SEBI numbering families:

* the classic ``SEBI/HO/<DEPT>/<SUB>/CIR/P/<YEAR>/<NUM>`` form,
* the newer PoD-era ``SEBI/HO/<DEPT>/<DEPT>-PoD-<n>/P/CIR/<YEAR>/<NUM>`` form,
* the pre-2016 short ``CIR/<DEPT>/<SUB>/<NUM>/<YEAR>`` form,
* and legacy ``<DEPT>/CIR/...`` variants.

``NEGATIVE_STRINGS`` are near-misses that must NOT match — a regex that
accepts these would flood the citation graph with false edges.
"""

from __future__ import annotations

REFERENCE_STRINGS: list[str] = [
    # --- classic SEBI/HO/.../CIR/P/<year>/<num> ---
    "SEBI/HO/MIRSD/MIRSD-PoD-1/P/CIR/2023/17",
    "SEBI/HO/MIRSD/MIRSD-PoD/CIR/P/2024/17",
    "SEBI/HO/CFD/PoD-2/P/CIR/2023/120",
    "SEBI/HO/CFD/CMD1/CIR/P/2020/110",
    "SEBI/HO/DDHS/DDHS-RACPOD1/P/CIR/2023/108",
    "SEBI/HO/MRD/DP/CIR/P/2016/110",
    "SEBI/HO/MRD2/DCAP/CIR/P/2021/0000000662",
    "SEBI/HO/IMD/IMD-PoD-1/P/CIR/2023/154",
    "SEBI/HO/IMD/DF2/CIR/P/2019/42",
    "SEBI/HO/OIAE/OIAE_IAD-1/P/CIR/2023/131",
    "SEBI/HO/ITD/ITD-PoD/CIR/P/2024/44",
    "SEBI/HO/AFD/AFD-PoD-1/P/CIR/2024/2",
    "SEBI/HO/DDHS/P/CIR/2022/0000000103",
    "SEBI/HO/LAD-NRO/GN/2023/119",
    "SEBI/HO/MIRSD/DOP/P/CIR/2022/119",
    "SEBI/HO/MIRSD/CRADT/CIR/P/2020/203",
    "SEBI/HO/CFD/DIL2/CIR/P/2021/0000000552",
    "SEBI/HO/DDHS/DDHS_Div1/P/CIR/2022/0000000103",
    "SEBI/HO/ISD/ISD-PoD-2/P/CIR/2024/56",
    "SEBI/HO/GSD/TAD/CIR/P/2019/89",
    # --- pre-2016 short form ---
    "CIR/MRD/DP/54/2017",
    "CIR/MIRSD/2/2016",
    "CIR/CFD/CMD/4/2015",
    "CIR/IMD/DF/14/2014",
    "CIR/MRD/DSA/33/2012",
    "CIR/OIAE/2/2013",
    "CIR/ISD/1/2011",
    "CIR/CFD/POLICY CELL/2/2015",
    # --- legacy department-first ---
    "MRD/DoP/SE/Cir-16/2010",
    "MIRSD/SE/Cir-21/2011",
    "IMD/FII&C/2010/07",
    "CFD/DIL/LISTING/2/2009",
    # --- newer PoD family, other departments ---
    "SEBI/HO/MIRSD/MIRSD-PoD-2/P/CIR/2024/89",
    "SEBI/HO/CFD/CFD-PoD-1/P/CIR/2024/154",
    "SEBI/HO/DDHS/DDHS-PoD-1/P/CIR/2024/47",
    "SEBI/HO/IMD/IMD-PoD-2/P/CIR/2024/12",
    "SEBI/HO/MRD/MRD-PoD-3/P/CIR/2024/61",
    "SEBI/HO/AFD/PoD/CIR/2023/97",
    "SEBI/HO/ISD/ISD-PoD-1/P/CIR/2023/117",
    "SEBI/HO/OIAE/OIAE_IAD-3/P/CIR/2024/29",
]

# Strings that superficially resemble a reference but are not one. A regex
# that matches these creates false citation edges.
NEGATIVE_STRINGS: list[str] = [
    "Regulation 32(1) of the LODR Regulations",
    "Section 11(1) of the SEBI Act, 1992",
    "Rule 19(2)(b) of the Securities Contracts Rules",
    "as per para 3.2.1 of this circular",
    "PAN ABCDE1234F",
    "the ratio was 2/3 in 2023",
    "T+1 settlement from January 2023",
    "ISIN INE002A01018",
    "https://www.sebi.gov.in/legal/circulars/index.html",
    "an amount of Rs. 10,000/- per annum",
]

assert len(REFERENCE_STRINGS) == 40, "the brief specifies a 40-reference fixture"
