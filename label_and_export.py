import sys, json
from graphify.build import build_from_json
from graphify.cluster import score_all
from graphify.analyze import god_nodes, surprising_connections, suggest_questions
from graphify.report import generate
from graphify.export import to_html
from pathlib import Path

extraction = json.loads(Path('graphify-out/.graphify_extract.json').read_text())
detection  = json.loads(Path('graphify-out/.graphify_detect.json').read_text())
analysis   = json.loads(Path('graphify-out/.graphify_analysis.json').read_text())

G = build_from_json(extraction)
communities = {int(k): v for k, v in analysis['communities'].items()}
cohesion = {int(k): v for k, v in analysis['cohesion'].items()}
tokens = {'input': extraction.get('input_tokens', 0), 'output': extraction.get('output_tokens', 0)}

labels = {
    0: "DESIGN.md Format Spec",
    1: "Productivity SaaS Tools",
    2: "Aerospace & EV Brands",
    3: "European Automotive",
    4: "Fintech & Crypto",
    5: "Web Dev Platforms",
    6: "Developer Infrastructure",
    7: "Luxury Automotive",
    8: "Open Source AI Models",
    9: "Consumer Entertainment",
    10: "Cutting-Edge AI Labs",
    11: "AI Model Hosting",
    12: "AI Platform Design",
    13: "Enterprise Technology",
    14: "Contribution Guidelines",
}
# Fill remaining communities with generic names
for cid in communities:
    if cid not in labels:
        nodes = communities[cid]
        node_labels = [G.nodes[n].get('label', n) for n in nodes[:2]]
        labels[cid] = ' & '.join(node_labels)[:40] if node_labels else f'Community {cid}'

questions = suggest_questions(G, communities, labels)
report = generate(G, communities, cohesion, labels, analysis['gods'], analysis['surprises'], detection, tokens, 'awesome-design-md', suggested_questions=questions)
Path('graphify-out/GRAPH_REPORT.md').write_text(report, encoding='utf-8')
Path('graphify-out/.graphify_labels.json').write_text(json.dumps({str(k): v for k, v in labels.items()}))
print('Report updated with community labels')

to_html(G, communities, 'graphify-out/graph.html', community_labels=labels or None)
print('graph.html written - open in any browser, no server needed')
print()
print('Outputs:')
print('  graphify-out/GRAPH_REPORT.md  - audit report')
print('  graphify-out/graph.json       - GraphRAG-ready JSON')
print('  graphify-out/graph.html       - interactive visualization')
