"""Generate the UNEP Ecological Collapse Briefing PDF for Exodus RPG."""

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm, cm
from reportlab.lib.colors import HexColor, black, white
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable,
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY

# Colors
DARK_BG = HexColor("#1a1a2e")
ACCENT = HexColor("#c41e3a")
ACCENT_DARK = HexColor("#8b1528")
HEADER_BG = HexColor("#2d2d44")
MUTED = HexColor("#666680")
TEXT = HexColor("#222233")
WARN_BG = HexColor("#fff3cd")
WARN_BORDER = HexColor("#d4a017")
CRIT_BG = HexColor("#f8d7da")
CRIT_BORDER = HexColor("#c41e3a")
LIGHT_BG = HexColor("#f4f4f8")

# Styles
STYLES = {
    "title": ParagraphStyle(
        "title", fontName="Helvetica-Bold", fontSize=22,
        textColor=ACCENT, alignment=TA_CENTER, spaceAfter=1*mm,
        leading=26,
    ),
    "subtitle": ParagraphStyle(
        "subtitle", fontName="Helvetica", fontSize=11,
        textColor=MUTED, alignment=TA_CENTER, spaceAfter=8*mm,
    ),
    "classified": ParagraphStyle(
        "classified", fontName="Helvetica-Bold", fontSize=14,
        textColor=ACCENT, alignment=TA_CENTER, spaceAfter=2*mm,
        spaceBefore=4*mm,
    ),
    "classified_sub": ParagraphStyle(
        "classified_sub", fontName="Helvetica", fontSize=8,
        textColor=MUTED, alignment=TA_CENTER, spaceAfter=8*mm,
    ),
    "section": ParagraphStyle(
        "section", fontName="Helvetica-Bold", fontSize=14,
        textColor=TEXT, spaceBefore=10*mm, spaceAfter=4*mm,
        borderPadding=(0, 0, 2*mm, 0),
    ),
    "hotspot_title": ParagraphStyle(
        "hotspot_title", fontName="Helvetica-Bold", fontSize=12,
        textColor=ACCENT, spaceBefore=6*mm, spaceAfter=2*mm,
    ),
    "hotspot_sub": ParagraphStyle(
        "hotspot_sub", fontName="Helvetica-Bold", fontSize=9,
        textColor=MUTED, spaceAfter=3*mm,
    ),
    "body": ParagraphStyle(
        "body", fontName="Helvetica", fontSize=9.5,
        textColor=TEXT, alignment=TA_JUSTIFY, spaceAfter=3*mm,
        leading=14,
    ),
    "body_bold": ParagraphStyle(
        "body_bold", fontName="Helvetica-Bold", fontSize=9.5,
        textColor=TEXT, spaceAfter=2*mm, leading=14,
    ),
    "bullet": ParagraphStyle(
        "bullet", fontName="Helvetica", fontSize=9,
        textColor=TEXT, leftIndent=12*mm, spaceAfter=1.5*mm,
        bulletIndent=6*mm, leading=13,
    ),
    "footer": ParagraphStyle(
        "footer", fontName="Helvetica", fontSize=7,
        textColor=MUTED, alignment=TA_CENTER,
    ),
    "page_header": ParagraphStyle(
        "page_header", fontName="Helvetica", fontSize=7,
        textColor=MUTED,
    ),
    "table_header": ParagraphStyle(
        "table_header", fontName="Helvetica-Bold", fontSize=8,
        textColor=white, alignment=TA_CENTER,
    ),
    "table_cell": ParagraphStyle(
        "table_cell", fontName="Helvetica", fontSize=8,
        textColor=TEXT, alignment=TA_CENTER,
    ),
    "table_cell_left": ParagraphStyle(
        "table_cell_left", fontName="Helvetica", fontSize=8,
        textColor=TEXT,
    ),
    "exec_body": ParagraphStyle(
        "exec_body", fontName="Helvetica", fontSize=10,
        textColor=TEXT, alignment=TA_JUSTIFY, spaceAfter=4*mm,
        leading=15,
    ),
    "warning_text": ParagraphStyle(
        "warning_text", fontName="Helvetica-Bold", fontSize=9,
        textColor=HexColor("#856404"), alignment=TA_CENTER,
    ),
    "critical_text": ParagraphStyle(
        "critical_text", fontName="Helvetica-Bold", fontSize=9,
        textColor=ACCENT, alignment=TA_CENTER,
    ),
}


def header_footer(canvas, doc):
    """Draw header and footer on each page."""
    canvas.saveState()
    w, h = A4

    # Top red line
    canvas.setStrokeColor(ACCENT)
    canvas.setLineWidth(2)
    canvas.line(15*mm, h - 12*mm, w - 15*mm, h - 12*mm)

    # Header text
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(15*mm, h - 10*mm,
                      "UNEP/IPCC JOINT EMERGENCY ASSESSMENT  |  CLASSIFICATION: EYES ONLY — WORLD LEADERS")

    canvas.drawRightString(w - 15*mm, h - 10*mm,
                           f"REF: UNEP-EA/2036-OMEGA-7  |  Page {doc.page}")

    # Bottom red line
    canvas.setStrokeColor(ACCENT)
    canvas.setLineWidth(1)
    canvas.line(15*mm, 18*mm, w - 15*mm, 18*mm)

    # Footer
    canvas.setFont("Helvetica", 6.5)
    canvas.setFillColor(MUTED)
    canvas.drawCentredString(w/2, 14*mm,
        "This document is classified under UN Security Protocol 7. "
        "Unauthorized distribution is a violation of Resolution 2847.")
    canvas.drawCentredString(w/2, 10*mm,
        "United Nations Environment Programme  |  Intergovernmental Panel on Climate Change  |  Joint Assessment Division")

    canvas.restoreState()


def build_pdf():
    """Build the report PDF."""
    filename = "/home/gorm/projects/exodus/media/news/bifrost_dispatch_omega7.pdf"
    import os
    os.makedirs(os.path.dirname(filename), exist_ok=True)

    doc = SimpleDocTemplate(
        filename, pagesize=A4,
        leftMargin=20*mm, rightMargin=20*mm,
        topMargin=20*mm, bottomMargin=25*mm,
    )

    story = []

    # ---- COVER / TITLE ----
    story.append(Spacer(1, 8*mm))

    story.append(Paragraph(
        "CLASSIFIED — EYES ONLY",
        STYLES["classified"],
    ))
    story.append(Paragraph(
        "Distribution restricted to heads of state and designated national security advisors",
        STYLES["classified_sub"],
    ))

    story.append(Spacer(1, 5*mm))
    story.append(HRFlowable(width="100%", thickness=2, color=ACCENT))
    story.append(Spacer(1, 8*mm))

    story.append(Paragraph(
        "GLOBAL BIOSPHERE",
        STYLES["title"],
    ))
    story.append(Paragraph(
        "INTEGRITY ASSESSMENT",
        STYLES["title"],
    ))
    story.append(Paragraph(
        "PROJECT OMEGA-7: ACCELERATED ECOLOGICAL COLLAPSE PROJECTIONS",
        ParagraphStyle("sub2", fontName="Helvetica-Bold", fontSize=11,
                       textColor=TEXT, alignment=TA_CENTER, spaceAfter=4*mm),
    ))
    story.append(Paragraph(
        "UNEP / IPCC Joint Emergency Assessment Division<br/>"
        "Reference: UNEP-EA/2036-OMEGA-7  |  Date: 3 February 2036<br/>"
        "Classification: EYES ONLY — Heads of State",
        STYLES["subtitle"],
    ))

    story.append(Spacer(1, 5*mm))
    story.append(HRFlowable(width="100%", thickness=1, color=MUTED))
    story.append(Spacer(1, 8*mm))

    # ---- EXECUTIVE SUMMARY ----
    story.append(Paragraph("EXECUTIVE SUMMARY", STYLES["section"]))
    story.append(HRFlowable(width="100%", thickness=0.5, color=MUTED))
    story.append(Spacer(1, 3*mm))

    story.append(Paragraph(
        "This assessment represents the consensus findings of 847 researchers across "
        "14 institutions operating under UNEP Emergency Protocol since November 2034. "
        "The conclusions contained herein supersede all prior IPCC projections, including "
        "AR9 (2035).",
        STYLES["exec_body"],
    ))

    # Critical warning box
    crit_data = [[Paragraph(
        "CRITICAL FINDING: Global biosphere carrying capacity is projected to sustain "
        "no more than 10-12% of the current human population within 8-12 years "
        "(median estimate: 2044). This represents a revision of 40+ years from prior "
        "AR9 worst-case scenarios. The acceleration is irreversible under all modelled "
        "intervention strategies.",
        STYLES["critical_text"],
    )]]
    crit_table = Table(crit_data, colWidths=[doc.width - 8*mm])
    crit_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), CRIT_BG),
        ("BOX", (0, 0), (-1, -1), 1.5, CRIT_BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 4*mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4*mm),
        ("LEFTPADDING", (0, 0), (-1, -1), 4*mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4*mm),
    ]))
    story.append(crit_table)
    story.append(Spacer(1, 5*mm))

    story.append(Paragraph(
        "Three compounding factors have converged to produce this revision:",
        STYLES["body"],
    ))

    factors = [
        ("<b>Tipping Point Cascade</b> — Seven of nine identified planetary boundaries "
         "have now been crossed. The transgression of three boundaries in rapid succession "
         "(biosphere integrity in 2033, novel entities in 2034, and ocean acidification "
         "threshold in late 2035) has triggered a non-linear acceleration that no prior "
         "model anticipated."),
        ("<b>Topsoil Depletion Crisis</b> — Industrial agriculture has reduced global "
         "topsoil depth by 40% since 1970. Remaining arable topsoil is now projected to "
         "lose productive capacity within 15-20 harvest cycles. Without functioning "
         "ecosystems to regenerate soil biomes, this process is effectively irreversible "
         "on human timescales."),
        ("<b>Systemic Energy-Ecology Feedback</b> — Global energy demand (driven in part "
         "by hyperscale AI data centres, desalination plants, and climate adaptation "
         "infrastructure) has increased freshwater diversion and thermal pollution to "
         "levels that actively suppress ecosystem recovery in 23 of 34 major watersheds."),
    ]
    for f in factors:
        story.append(Paragraph(f, STYLES["bullet"], bulletText="\u2022"))

    story.append(Spacer(1, 4*mm))

    # Warning box
    warn_data = [[Paragraph(
        "NOTE: Previous disclosure timelines assumed gradual public communication "
        "beginning 2039. This assessment necessitates immediate revision of "
        "continuity-of-civilisation planning across all UN member states.",
        STYLES["warning_text"],
    )]]
    warn_table = Table(warn_data, colWidths=[doc.width - 8*mm])
    warn_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), WARN_BG),
        ("BOX", (0, 0), (-1, -1), 1, WARN_BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 3*mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3*mm),
        ("LEFTPADDING", (0, 0), (-1, -1), 4*mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4*mm),
    ]))
    story.append(warn_table)

    # ---- HOTSPOT OVERVIEW TABLE ----
    story.append(Paragraph("CRITICAL HOTSPOT OVERVIEW", STYLES["section"]))
    story.append(HRFlowable(width="100%", thickness=0.5, color=MUTED))
    story.append(Spacer(1, 3*mm))

    story.append(Paragraph(
        "Five regions have been designated Priority Alpha collapse zones based on "
        "the rate of biosphere degradation, population exposure, and cascading risk "
        "to adjacent systems. Each zone exhibits self-reinforcing feedback loops that "
        "preclude recovery under any currently feasible intervention.",
        STYLES["body"],
    ))

    # Summary table
    t_header = [
        Paragraph("ZONE", STYLES["table_header"]),
        Paragraph("REGION", STYLES["table_header"]),
        Paragraph("STATUS", STYLES["table_header"]),
        Paragraph("POP. EXPOSED", STYLES["table_header"]),
        Paragraph("COLLAPSE<br/>HORIZON", STYLES["table_header"]),
    ]
    t_rows = [
        ["H-1", "Ukraine / Black Sea Basin", "ACTIVE COLLAPSE", "112M", "Ongoing"],
        ["H-2", "Southern Europe / Mediterranean", "NEAR-TOTAL FAILURE", "185M", "2037-2038"],
        ["H-3", "Amazon Basin / South America", "TIPPING POINT CROSSED", "420M", "2038-2040"],
        ["H-4", "South & Southeast Asia — Monsoon Belt", "CRITICAL INSTABILITY", "2.1B", "2039-2041"],
        ["H-5", "Sub-Saharan Sahel / West Africa", "ACCELERATING FAILURE", "540M", "2037-2039"],
    ]
    t_data = [t_header]
    for row in t_rows:
        t_data.append([
            Paragraph(row[0], STYLES["table_cell"]),
            Paragraph(row[1], STYLES["table_cell_left"]),
            Paragraph(f'<font color="#c41e3a"><b>{row[2]}</b></font>', STYLES["table_cell"]),
            Paragraph(row[3], STYLES["table_cell"]),
            Paragraph(row[4], STYLES["table_cell"]),
        ])

    col_w = [12*mm, 52*mm, 38*mm, 28*mm, 28*mm]
    t = Table(t_data, colWidths=col_w, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, MUTED),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, LIGHT_BG]),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5*mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5*mm),
        ("LEFTPADDING", (0, 0), (-1, -1), 2*mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2*mm),
    ]))
    story.append(t)

    # ---- HOTSPOT DETAILS ----
    hotspots = [
        {
            "id": "H-1",
            "title": "UKRAINE / BLACK SEA BASIN",
            "subtitle": "Status: ACTIVE COLLAPSE  |  Classification: War-Induced Ecological Catastrophe",
            "paragraphs": [
                "The Russia-Ukraine conflict (2022-present) has produced the largest "
                "concentrated environmental contamination event since Chernobyl. Fourteen years "
                "of sustained artillery bombardment, the deliberate destruction of the "
                "Kakhovka Dam (June 2023), and widespread deployment of munitions containing "
                "depleted uranium have rendered approximately 30% of Ukraine's previously "
                "arable land permanently unsuitable for food production.",

                "The Kakhovka Dam collapse alone contaminated 80,000+ hectares of farmland "
                "with industrial chemicals, heavy metals, and radioactive sediment from the "
                "Zaporizhzhia Nuclear Power Plant cooling reservoir. Downstream effects have "
                "devastated Black Sea fisheries, with commercial fish stocks in the northwestern "
                "Black Sea declining by 91% since 2023.",
            ],
            "factors": [
                "<b>Soil contamination:</b> An estimated 174,000 sq km of Ukrainian territory "
                "is contaminated by unexploded ordnance, cluster munitions, and chemical "
                "residues. Demining at current capacity would require 750+ years.",
                "<b>Aquifer poisoning:</b> Heavy metals and nitrates from munitions have "
                "penetrated the Dnieper Basin aquifer system, affecting drinking water for "
                "an estimated 35 million people across Ukraine, Moldova, and Romania.",
                "<b>Black Sea dead zone expansion:</b> Nutrient runoff from destroyed "
                "agricultural infrastructure, combined with dam collapse sediment, has "
                "expanded the Black Sea hypoxic zone by 340% — now the largest marine "
                "dead zone on Earth.",
                "<b>Cascading food export failure:</b> Ukraine previously supplied 10% of "
                "global wheat exports and 15% of sunflower oil. This capacity is now "
                "permanently lost, creating downstream food insecurity across North Africa "
                "and the Middle East.",
            ],
        },
        {
            "id": "H-2",
            "title": "SOUTHERN EUROPE / MEDITERRANEAN",
            "subtitle": "Status: NEAR-TOTAL FAILURE  |  Classification: Aridification Collapse",
            "paragraphs": [
                "The Mediterranean Basin — identified since AR5 (2014) as a climate change "
                "hotspot — has crossed the threshold from 'accelerated degradation' to "
                "'systemic failure' as of late 2035. Average temperatures in southern Spain, "
                "Italy, and Greece now exceed pre-industrial levels by 3.4°C (vs. 2.1°C "
                "global average), triggering a self-reinforcing aridification cycle.",

                "The 2035 growing season in the Iberian Peninsula recorded the lowest "
                "agricultural yields since records began in 1861. Olive oil production — "
                "Spain supplies 45% of global output — has collapsed by 94% over six "
                "consecutive harvest failures. Italian durum wheat production is down 67%. "
                "Greek agricultural exports have effectively ceased.",
            ],
            "factors": [
                "<b>Desertification advance:</b> The Sahara Desert boundary has shifted "
                "north by 140 km in the past decade. Southern Spain (Andalusia, Murcia) "
                "and Sicily now meet the UNEP definition of desert climate. This is "
                "irreversible — topsoil loss prevents reforestation even under cooler "
                "conditions.",
                "<b>Freshwater crisis:</b> Reservoir levels across Spain, Portugal, and "
                "southern France are at 11-18% capacity. The Tagus, Ebro, and Po rivers "
                "have recorded zero-flow events annually since 2033.",
                "<b>Wildfire feedback loop:</b> The 2034-2035 Mediterranean fire seasons "
                "burned 6.8 million hectares — 5x the prior decade average. Burned landscapes "
                "lose water retention capacity, accelerating desertification of adjacent "
                "areas in a self-reinforcing cycle.",
                "<b>Marine ecosystem collapse:</b> Mediterranean Sea surface temperatures "
                "exceeded 31°C for 62 consecutive days in summer 2035. Mass mortality events "
                "have eliminated 90%+ of Posidonia oceanica seagrass meadows, collapsing "
                "the marine food web that supports 650+ commercially harvested species.",
            ],
        },
        {
            "id": "H-3",
            "title": "AMAZON BASIN / SOUTH AMERICA",
            "subtitle": "Status: TIPPING POINT CROSSED  |  Classification: Rainforest-Savanna Transition",
            "paragraphs": [
                "In September 2035, satellite monitoring confirmed what ecological modellers "
                "had feared since 2031: the Amazon rainforest has crossed the dieback tipping "
                "point. Deforestation (25% of original cover lost) combined with three "
                "consecutive drought years has broken the forest's hydrological cycle — the "
                "system by which the Amazon generates 50% of its own rainfall through "
                "transpiration.",

                "The Amazon currently produces 6% of global oxygen and stores approximately "
                "150-200 billion tonnes of carbon. The transition from rainforest to degraded "
                "savanna is now projected to release this carbon over 15-30 years, adding an "
                "estimated 0.8-1.2°C to global temperatures — independent of all other "
                "emission sources.",
            ],
            "factors": [
                "<b>Hydrological cycle failure:</b> Rainfall in the eastern Amazon has "
                "declined 34% since 2028. The 'flying rivers' — atmospheric moisture "
                "corridors that carry Amazon transpiration to southern Brazil and Argentina — "
                "have weakened by an estimated 45%, threatening agriculture across the "
                "entire Southern Cone.",
                "<b>Carbon bomb:</b> Forest dieback is converting the Amazon from carbon "
                "sink to carbon source. Current measurements show net emissions of 1.1 GtCO2 "
                "per year from the basin — equivalent to Japan's total annual emissions.",
                "<b>Biodiversity catastrophe:</b> The Amazon contains 10% of all known "
                "species. Mass die-offs of keystone species (particularly pollinators and "
                "seed dispersers) are preventing forest regeneration even in areas not "
                "directly deforested.",
                "<b>Agricultural cascade:</b> Southern Brazil, Paraguay, and Argentina — "
                "which collectively produce 14% of global food exports — depend on Amazon-"
                "derived rainfall. Crop failures in these regions are projected to reach "
                "40-60% by 2039.",
            ],
        },
        {
            "id": "H-4",
            "title": "SOUTH & SOUTHEAST ASIA — MONSOON BELT",
            "subtitle": "Status: CRITICAL INSTABILITY  |  Classification: Monsoon Disruption / Breadbasket Failure",
            "paragraphs": [
                "The Asian monsoon system — which directly sustains 2.1 billion people and "
                "produces 90% of the world's rice — is exhibiting unprecedented instability. "
                "The 2035 monsoon arrived 23 days late, delivered 31% less total rainfall, "
                "but concentrated in extreme precipitation events that caused catastrophic "
                "flooding in Bangladesh, Myanmar, and eastern India while drought conditions "
                "persisted across the Indo-Gangetic Plain.",

                "Himalayan glaciers — the 'Third Pole' that feeds the Ganges, Brahmaputra, "
                "Mekong, and Yangtze river systems — have lost 55% of their mass since 2000. "
                "Peak water (maximum meltwater contribution) has been reached for the Ganges "
                "and Indus basins. River flows are projected to decline 30-50% by 2044, "
                "affecting irrigation systems that feed 800 million people.",
            ],
            "factors": [
                "<b>Rice production crisis:</b> Global rice yields declined 12% in 2035 — "
                "the largest single-year drop ever recorded. Paddy fields in Vietnam's "
                "Mekong Delta are being inundated by saltwater intrusion as sea levels "
                "rise and freshwater flows diminish.",
                "<b>Groundwater exhaustion:</b> India's Punjab and Haryana states — the "
                "country's primary wheat and rice producing regions — are extracting "
                "groundwater at 3x the recharge rate. Aquifer depletion is projected to "
                "make irrigated agriculture impossible in these regions by 2040-2042.",
                "<b>Pollinator collapse:</b> Southeast Asia has lost an estimated 62% of "
                "wild pollinator populations since 2024, driven by pesticide use, habitat "
                "loss, and thermal stress. This threatens fruit and vegetable production "
                "across the region.",
                "<b>Mass displacement pressure:</b> Bangladesh alone is projected to produce "
                "18-25 million climate refugees by 2041, with cascading destabilisation "
                "effects across the region.",
            ],
        },
        {
            "id": "H-5",
            "title": "SUB-SAHARAN SAHEL / WEST AFRICA",
            "subtitle": "Status: ACCELERATING FAILURE  |  Classification: Desertification / Ecosystem Cascade",
            "paragraphs": [
                "The Sahel — the semi-arid transition zone between the Sahara and the "
                "tropical forests of West Africa — has been under ecological stress for "
                "decades. However, the convergence of accelerating desertification, "
                "population growth (the region's population has doubled since 2012), and "
                "the collapse of Lake Chad has created a crisis of existential proportions.",

                "Lake Chad, once the sixth-largest lake on Earth and the primary water "
                "source for 40 million people, has shrunk by 95% since 1963. As of 2036, "
                "it is functionally extinct as a freshwater ecosystem. The UN considers "
                "the Lake Chad Basin the single largest ecological displacement crisis "
                "currently unfolding.",
            ],
            "factors": [
                "<b>Sahara expansion:</b> The Sahara is advancing southward at 48 km/year "
                "in the Sahel corridor — 3x the rate observed in the 1990s. The Great Green "
                "Wall initiative has achieved only 4% of its target and cannot keep pace "
                "with the advance.",
                "<b>Soil exhaustion:</b> Traditional farming practices depended on long "
                "fallow cycles. Population pressure has eliminated fallow periods entirely, "
                "and 65% of Sahelian agricultural land is now classified as severely degraded.",
                "<b>Conflict-ecology nexus:</b> Resource competition over shrinking arable "
                "land and water access is a primary driver of armed conflict across the "
                "Sahel (Mali, Burkina Faso, Niger, Nigeria, Chad). Conflict in turn prevents "
                "land management and conservation efforts, creating a self-reinforcing "
                "collapse cycle.",
                "<b>Migration cascade:</b> An estimated 135 million people in the Sahel "
                "face acute food insecurity as of January 2036. Projected displacement "
                "of 60-80 million people by 2041 would represent the largest migration "
                "event in human history.",
            ],
        },
    ]

    for hs in hotspots:
        story.append(Spacer(1, 6*mm))
        story.append(Paragraph(f'{hs["id"]}: {hs["title"]}', STYLES["hotspot_title"]))
        story.append(Paragraph(hs["subtitle"], STYLES["hotspot_sub"]))

        for p in hs["paragraphs"]:
            story.append(Paragraph(p, STYLES["body"]))

        story.append(Paragraph("<b>Key Contributing Factors:</b>", STYLES["body_bold"]))
        for f in hs["factors"]:
            story.append(Paragraph(f, STYLES["bullet"], bulletText="\u2022"))

    # ---- CONCLUSIONS ----
    story.append(PageBreak())
    story.append(Paragraph("CONCLUSIONS AND PROJECTIONS", STYLES["section"]))
    story.append(HRFlowable(width="100%", thickness=0.5, color=MUTED))
    story.append(Spacer(1, 3*mm))

    story.append(Paragraph(
        "The five hotspots detailed above are not isolated crises. They represent "
        "interconnected nodes in a global system undergoing cascading failure. The "
        "loss of Ukrainian grain exports destabilises North Africa. Mediterranean "
        "collapse drives migration into Northern Europe. Amazon dieback reduces "
        "rainfall in South America's breadbasket. Monsoon disruption threatens half "
        "the world's rice supply. Sahel desertification generates displacement pressure "
        "across two continents.",
        STYLES["body"],
    ))

    story.append(Paragraph(
        "The assessment panel has modelled 340 intervention scenarios, ranging from "
        "aggressive geoengineering to total industrial decarbonisation. <b>No modelled "
        "scenario reverses or halts the cascade within a timeframe that prevents "
        "civilisational-scale food system failure.</b> The most optimistic intervention "
        "pathway extends the timeline by approximately 3-5 years.",
        STYLES["body"],
    ))

    # Final projection table
    story.append(Spacer(1, 3*mm))
    story.append(Paragraph("<b>Global Food Production Capacity Projections</b>",
                           STYLES["body_bold"]))

    proj_header = [
        Paragraph("YEAR", STYLES["table_header"]),
        Paragraph("CARRYING CAPACITY<br/>(% of 2036 pop.)", STYLES["table_header"]),
        Paragraph("FOOD DEFICIT<br/>(billions)", STYLES["table_header"]),
        Paragraph("STATUS", STYLES["table_header"]),
    ]
    proj_rows = [
        ["2036", "78%", "1.8B", "Current"],
        ["2038", "54%", "3.7B", "Critical"],
        ["2040", "33%", "5.4B", "Systemic Collapse"],
        ["2042", "19%", "6.5B", "Civilisational Crisis"],
        ["2044", "10-12%", "7.1B", "Terminal"],
    ]
    proj_data = [proj_header]
    for row in proj_rows:
        color = "#c41e3a" if row[0] in ("2042", "2044") else "#856404" if row[0] in ("2038", "2040") else "#222233"
        proj_data.append([
            Paragraph(row[0], STYLES["table_cell"]),
            Paragraph(f'<font color="{color}"><b>{row[1]}</b></font>', STYLES["table_cell"]),
            Paragraph(row[2], STYLES["table_cell"]),
            Paragraph(f'<font color="{color}">{row[3]}</font>', STYLES["table_cell"]),
        ])

    pt = Table(proj_data, colWidths=[25*mm, 45*mm, 35*mm, 45*mm], repeatRows=1)
    pt.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, MUTED),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, LIGHT_BG]),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5*mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5*mm),
    ]))
    story.append(pt)

    story.append(Spacer(1, 6*mm))

    # Recommendations
    story.append(Paragraph("RECOMMENDED IMMEDIATE ACTIONS", STYLES["section"]))
    story.append(HRFlowable(width="100%", thickness=0.5, color=MUTED))
    story.append(Spacer(1, 3*mm))

    recs = [
        "<b>Immediate classification review:</b> This assessment must remain restricted "
        "until coordinated public communication strategies are established. Premature "
        "disclosure risks uncontrollable panic and market collapse.",
        "<b>Activate continuity-of-species protocols:</b> All viable options for "
        "ensuring long-term human survival — including but not limited to orbital "
        "habitation, off-world colonisation, and deep-bunker preservation programs — "
        "must be evaluated at the highest priority level.",
        "<b>Emergency food stockpiling:</b> Strategic reserves should be expanded "
        "immediately. Current global reserves represent 74 days of consumption.",
        "<b>International coordination framework:</b> A new intergovernmental body "
        "with executive authority is required to coordinate response at the necessary "
        "scale and speed. Existing UN mechanisms are insufficient.",
        "<b>Accelerate alternative food research:</b> Massive investment in synthetic "
        "biology, vertical farming, and alternative protein is required, though these "
        "technologies cannot scale sufficiently to close the projected deficit.",
    ]
    for r in recs:
        story.append(Paragraph(r, STYLES["bullet"], bulletText="\u2022"))

    story.append(Spacer(1, 8*mm))
    story.append(HRFlowable(width="60%", thickness=1, color=ACCENT))
    story.append(Spacer(1, 4*mm))

    story.append(Paragraph(
        "END OF REPORT",
        ParagraphStyle("end", fontName="Helvetica-Bold", fontSize=10,
                       textColor=MUTED, alignment=TA_CENTER, spaceAfter=2*mm),
    ))
    story.append(Paragraph(
        "UNEP-EA/2036-OMEGA-7  |  3 February 2036  |  EYES ONLY",
        ParagraphStyle("end2", fontName="Helvetica", fontSize=8,
                       textColor=MUTED, alignment=TA_CENTER),
    ))

    doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)
    print(f"PDF generated: {filename}")


if __name__ == "__main__":
    build_pdf()
