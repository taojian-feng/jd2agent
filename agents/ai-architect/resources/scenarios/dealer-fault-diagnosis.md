# Scenario: Dealer Service Fault Diagnosis (fictional; mock data only)

A heavy-equipment manufacturer's dealer network services engines and machines in the field.
When a machine reports a fault code, a service technician spends 2–4 hours cross-referencing
service manuals, recent telematics alerts, and the machine's repair history before deciding
what to inspect or replace. Repeat visits happen when the first diagnosis is wrong.

The business wants an assistant that, given a machine serial number and fault code, proposes a
likely root cause and the next inspection or repair steps. Every recommendation must cite the
manual section, alert, or past repair it relies on, because technicians and warranty auditors
need to verify it. The assistant must not create or close work orders on its own; a technician
approves any work order it drafts. Technicians use tablets in the field, so answers should come
back within about 30 seconds. Service manuals are updated monthly; telematics arrive continuously;
repair history lives in the dealer business system. Access to repair history is restricted to the
dealer that performed the work.
