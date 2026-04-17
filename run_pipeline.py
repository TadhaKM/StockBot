import sys, json
from graphify.build import build_from_json
from graphify.cluster import cluster, score_all
from graphify.analyze import god_nodes, surprising_connections, suggest_questions
from graphify.report import generate
from graphify.export import to_json, to_html
from pathlib import Path

# Load data
sem = json.loads(Path('graphify-out/.graphify_semantic.json').read_text())
detection = json.loads(Path('graphify-out/.graphify_detect.json').read_text())

# Add required fields
sem.setdefault('input_tokens', 0)
sem.setdefault('output_tokens', 0)

# Save as extract file (required by later steps)
Path('graphify-out/.graphify_extract.json').write_text(json.dumps(sem, indent=2))

G = build_from_json(sem)
print(f'Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges')

communities = cluster(G)
cohesion = score_all(G, communities)
tokens = {'input': sem.get('input_tokens', 0), 'output': sem.get('output_tokens', 0)}
gods = god_nodes(G)
surprises = surprising_connections(G, communities)
labels = {cid: 'Community ' + str(cid) for cid in communities}
questions = suggest_questions(G, communities, labels)

report = generate(G, communities, cohesion, labels, gods, surprises, detection, tokens, 'awesome-design-md', suggested_questions=questions)
Path('graphify-out/GRAPH_REPORT.md').write_text(report, encoding='utf-8')
to_json(G, communities, 'graphify-out/graph.json')

analysis = {
    'communities': {str(k): v for k, v in communities.items()},
    'cohesion': {str(k): v for k, v in cohesion.items()},
    'gods': gods,
    'surprises': surprises,
    'questions': questions,
}
Path('graphify-out/.graphify_analysis.json').write_text(json.dumps(analysis, indent=2))
print(f'Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges, {len(communities)} communities')
print(f'Top nodes: {[G.nodes[g["id"]].get("label", g["id"]) for g in gods[:5]]}')
