# Scenario: Contract Review Agent in a Software Product (fictional; mock data only)

An enterprise software vendor sells a contract lifecycle management product to about 300 corporate customers. Its
customers' legal teams review incoming supplier contracts against their own playbooks: which clauses are acceptable,
which need a fallback position, and which must go to a lawyer. A first review takes a paralegal 1–3 hours per
contract, and volume spikes to about 4,000 contracts a day across all customers at quarter end.

The vendor wants to ship a contract review agent inside the product. Given a contract and the customer's playbook,
it finds each clause the playbook covers, compares it with the playbook position, proposes a redline with the
playbook rule it applies, and lists clauses that need a lawyer. A comparison tool runs Python on the uploaded Word
files to produce the redlined document. The agent never sends anything to the counterparty; a person on the
customer's legal team accepts or rejects every redline. Every proposed change must cite the playbook rule and the
contract clause it relies on.

Each customer's contracts and playbooks are confidential to that customer, and several customers compete with each
other. The vendor wants to serve open-weight models on its own GPU cluster to control cost and keep data in its
cloud, and its machine learning team proposes fine-tuning a model on redlines that customers accepted. Product
management wants the first redline back within 60 seconds for a 20-page contract, and a cost per contract the
pricing team can plan around. The vendor's security team will not approve release without a documented evaluation,
including adversarial contracts that try to instruct the agent.
