-- ================================================================
-- Clerasense – Seed Data (verified, source-referenced)
-- Minimal dataset for MVP demonstration.
-- ================================================================

-- 1. Insert authoritative sources first
INSERT INTO sources (source_id, authority, document_title, publication_year, url) VALUES
(1, 'FDA', 'FDA Approved Drug Products – Metformin Hydrochloride', 2023, 'https://www.accessdata.fda.gov/drugsatfda_docs/label/2023/020357s043lbl.pdf'),
(2, 'FDA', 'FDA Approved Drug Products – Lisinopril', 2023, 'https://www.accessdata.fda.gov/drugsatfda_docs/label/2023/019777s075lbl.pdf'),
(3, 'FDA', 'FDA Approved Drug Products – Atorvastatin Calcium', 2023, 'https://www.accessdata.fda.gov/drugsatfda_docs/label/2023/020702s073lbl.pdf'),
(4, 'FDA', 'FDA Approved Drug Products – Amoxicillin', 2023, 'https://www.accessdata.fda.gov/drugsatfda_docs/label/2023/050542s042lbl.pdf'),
(5, 'WHO', 'WHO Model List of Essential Medicines – 23rd List', 2023, 'https://www.who.int/publications/i/item/WHO-MHP-HPS-EML-2023.02'),
(6, 'FDA', 'FDA Approved Drug Products – Amlodipine Besylate', 2023, 'https://www.accessdata.fda.gov/drugsatfda_docs/label/2023/019787s064lbl.pdf'),
(7, 'CMS', 'Medicare Part D Formulary Reference', 2024, 'https://www.cms.gov/Medicare/Prescription-Drug-Coverage'),
(8, 'FDA', 'FDA Drug Interaction Guidance Documents', 2023, 'https://www.fda.gov/drugs/drug-interactions-labeling');

-- 2. Drugs
INSERT INTO drugs (id, generic_name, brand_names, drug_class, mechanism_of_action, source_id) VALUES
(1, 'Metformin', '{"Glucophage","Fortamet","Riomet"}', 'Biguanide', 'Decreases hepatic glucose production, decreases intestinal absorption of glucose, and improves insulin sensitivity by increasing peripheral glucose uptake and utilization.', 1),
(2, 'Lisinopril', '{"Prinivil","Zestril"}', 'ACE Inhibitor', 'Inhibits angiotensin-converting enzyme (ACE), preventing conversion of angiotensin I to angiotensin II, leading to decreased vasopressor activity and aldosterone secretion.', 2),
(3, 'Atorvastatin', '{"Lipitor"}', 'HMG-CoA Reductase Inhibitor (Statin)', 'Selectively and competitively inhibits HMG-CoA reductase, the rate-limiting enzyme in cholesterol biosynthesis.', 3),
(4, 'Amoxicillin', '{"Amoxil","Trimox"}', 'Aminopenicillin', 'Inhibits bacterial cell wall synthesis by binding to penicillin-binding proteins, leading to cell lysis and death.', 4),
(5, 'Amlodipine', '{"Norvasc"}', 'Calcium Channel Blocker (Dihydropyridine)', 'Inhibits transmembrane influx of calcium ions into vascular smooth muscle and cardiac muscle, resulting in peripheral arterial vasodilation.', 6);

-- 3. Indications
INSERT INTO indications (drug_id, approved_use, source_id) VALUES
(1, 'Type 2 diabetes mellitus – as monotherapy or in combination with other antidiabetic agents, including insulin, to improve glycemic control.', 1),
(1, 'Prevention or delay of type 2 diabetes in patients with prediabetes (off-label use documented in ADA guidelines).', 5),
(2, 'Hypertension – treatment of high blood pressure, alone or in combination with other antihypertensive agents.', 2),
(2, 'Heart failure – adjunctive therapy for the management of heart failure.', 2),
(2, 'Acute myocardial infarction – hemodynamically stable patients within 24 hours to improve survival.', 2),
(3, 'Primary hyperlipidemia and mixed dyslipidemia – as adjunct to diet therapy.', 3),
(3, 'Prevention of cardiovascular disease – reduction of risk of MI, stroke, revascularization, and angina in patients with multiple risk factors.', 3),
(4, 'Infections of the ear, nose, throat, genitourinary tract, skin, and lower respiratory tract caused by susceptible organisms.', 4),
(4, 'Helicobacter pylori eradication – in combination with other agents for treatment of H. pylori infection and duodenal ulcer disease.', 4),
(5, 'Hypertension – treatment alone or in combination with other antihypertensive agents.', 6),
(5, 'Chronic stable angina and confirmed or suspected vasospastic angina.', 6);

-- 4. Dosage guidelines
INSERT INTO dosage_guidelines (drug_id, adult_dosage, pediatric_dosage, renal_adjustment, hepatic_adjustment, overdose_info, underdose_info, administration_info, source_id) VALUES
(1, 'Initial: 500 mg orally twice daily or 850 mg once daily. Max: 2550 mg/day in divided doses.', 'Age ≥10 years: 500 mg orally twice daily. Max: 2000 mg/day.', 'eGFR 30-45: Initiation not recommended; may continue if already on therapy with monitoring. eGFR <30: Contraindicated.', 'Avoid use in patients with hepatic impairment due to risk of lactic acidosis.',
'OVERDOSE — Signs & Symptoms: Hypoglycemia has not occurred with metformin alone at doses up to 85 g, but lactic acidosis has occurred. Symptoms include malaise, myalgias, respiratory distress, somnolence, and abdominal pain. Laboratory findings may include decreased blood pH, elevated serum lactate (>5 mmol/L), increased anion gap, and elevated lactate/pyruvate ratio. Severity: Potentially fatal — lactic acidosis mortality rate is approximately 50%. Management: Discontinue metformin immediately. Institute general supportive measures. Hemodialysis is recommended as it corrects acidosis and removes accumulated metformin (clearance up to 170 mL/min). Monitor serum lactate, blood gases, and electrolytes.',
'UNDERDOSE / MISSED DOSE — Effects: Subtherapeutic dosing leads to inadequate glycemic control, with fasting glucose >130 mg/dL and HbA1c above target (>7%). Chronic underdosing increases risk of long-term diabetic complications including neuropathy, nephropathy, and retinopathy. Recommended range: 1500–2550 mg/day for therapeutic effect; doses below 1000 mg/day are generally subtherapeutic. Missed dose: Take as soon as remembered unless close to next dose — do not double up. Severity: Non-life-threatening acutely, but chronic underdosing results in progressive end-organ damage.',
'Route: Oral. Available forms: Immediate-release tablets (500 mg, 850 mg, 1000 mg); extended-release tablets (500 mg, 750 mg, 1000 mg); oral solution (500 mg/5 mL). Administration: Take with meals to reduce gastrointestinal side effects. Swallow extended-release tablets whole — do not crush, cut, or chew. Oral solution may be used for patients who cannot swallow tablets. Storage: Store at 20–25°C (68–77°F); excursions permitted to 15–30°C. Keep container tightly closed. Protect from light and moisture.',
1),
(2, 'Initial: 10 mg orally once daily. Usual maintenance: 20-40 mg/day. Max: 80 mg/day.', 'Age ≥6 years: Initial 0.07 mg/kg once daily (up to 5 mg). Max: 0.61 mg/kg/day or 40 mg/day.', 'CrCl 10-30 mL/min: Initial 2.5-5 mg/day. Hemodialysis: 2.5 mg on dialysis days.', 'No specific adjustment; use with caution.',
'OVERDOSE — Signs & Symptoms: Severe hypotension is the primary manifestation. Other symptoms include electrolyte imbalances (hyperkalemia), renal failure, bradycardia, and stupor. Single doses above 80 mg have caused severe hypotension. Severity: Can be life-threatening due to cardiovascular collapse. Management: IV normal saline infusion is first-line for hypotension. Angiotensin II (Giapreza) may be considered for refractory cases. Lisinopril is removable by hemodialysis. Monitor blood pressure, serum potassium, and renal function closely for at least 24 hours.',
'UNDERDOSE / MISSED DOSE — Effects: Inadequate blood pressure control; sustained systolic BP >140 mmHg increases stroke risk by 2-3× and heart failure risk. In patients with heart failure, subtherapeutic ACE inhibition leads to disease progression. Recommended range: 20–40 mg/day for most adults; doses below 10 mg/day are generally subtherapeutic except in renal impairment. Missed dose: Take as soon as remembered; skip if near next dose. Severity: Non-acutely dangerous but chronic underdosing leads to cumulative cardiovascular damage.',
'Route: Oral. Available forms: Tablets (2.5 mg, 5 mg, 10 mg, 20 mg, 30 mg, 40 mg); oral solution (1 mg/mL). Administration: May be taken with or without food. Administer once daily at approximately the same time each day. Tablets may be crushed if needed. For oral solution, shake well before each use. Storage: Store at 20–25°C (68–77°F); excursions permitted to 15–30°C. Protect from moisture and freezing.',
2),
(3, 'Initial: 10-20 mg once daily. Usual range: 10-80 mg/day.', 'Age 10-17 years (heterozygous familial hypercholesterolemia): 10 mg once daily. Max: 20 mg/day.', 'No dose adjustment required.', 'Contraindicated in active liver disease or unexplained persistent transaminase elevations.',
'OVERDOSE — Signs & Symptoms: No specific antidote exists. There is no additional benefit above 80 mg/day and toxicity increases. Symptoms may include severe myopathy, rhabdomyolysis (CK >10× ULN), hepatotoxicity (transaminase elevation >3× ULN), and gastrointestinal distress. Severity: Rhabdomyolysis can be fatal — causes acute kidney injury from myoglobin release. Management: General supportive care. Monitor CK levels, hepatic transaminases, and renal function. Hemodialysis is not expected to be effective due to extensive plasma protein binding (~98%).',
'UNDERDOSE / MISSED DOSE — Effects: Subtherapeutic statin dosing leads to failure to achieve LDL-C goals (target <70 mg/dL for high-risk patients per ACC/AHA guidelines). Inadequate LDL reduction increases risk of atherosclerotic cardiovascular events (MI, stroke). Recommended range: 10–80 mg/day; 40–80 mg is high-intensity therapy achieving ≥50% LDL reduction. Missed dose: Take as soon as remembered if on the same day; skip if it is almost time for next day dose. Severity: Non-acutely dangerous, but statin non-adherence is associated with 25% increased cardiovascular event risk.',
'Route: Oral. Available forms: Tablets (10 mg, 20 mg, 40 mg, 80 mg). Administration: May be taken with or without food, at any time of day. Swallow tablets whole with water. Consistent daily dosing is recommended. Unlike some other statins, atorvastatin does not need to be taken at bedtime due to its long half-life (14 hours for active metabolites). Storage: Store at 20–25°C (68–77°F). Keep in original container. Protect from light and moisture.',
3),
(4, '250-500 mg orally every 8 hours, or 500-875 mg every 12 hours depending on infection severity.', '20-40 mg/kg/day in divided doses every 8 hours, or 25-45 mg/kg/day every 12 hours.', 'GFR 10-30: 250-500 mg every 12 hours. GFR <10: 250-500 mg every 24 hours.', 'No specific adjustment provided in labeling.',
'OVERDOSE — Signs & Symptoms: Gastrointestinal symptoms including nausea, vomiting, and diarrhea are most common. Crystalluria leading to acute renal failure can occur at very high doses. Neurotoxicity (seizures, encephalopathy) is possible, particularly with renal impairment. Allergic/anaphylactic reactions may also present. Severity: Generally low toxicity — fatalities from amoxicillin overdose alone are rare. Management: Maintain adequate fluid intake and urinary output to reduce risk of crystalluria. Activated charcoal may be given if ingestion was recent (within 1 hour). Hemodialysis can remove amoxicillin from circulation. Monitor renal function and electrolytes.',
'UNDERDOSE / MISSED DOSE — Effects: Subtherapeutic antibiotic levels fail to achieve minimum inhibitory concentration (MIC) against target bacteria, leading to treatment failure. More critically, inconsistent dosing promotes antibiotic resistance by exposing bacteria to sub-lethal concentrations — a major public health concern. Recommended range: 750–1500 mg/day (mild-moderate), up to 3000 mg/day (severe infections). Missed dose: Take immediately when remembered; if almost time for next dose, take the missed dose and resume schedule. Severity: Treatment failure is the primary risk; sepsis in severe infections if underdosed significantly.',
'Route: Oral. Available forms: Capsules (250 mg, 500 mg); tablets (500 mg, 875 mg); chewable tablets (125 mg, 250 mg); oral suspension (125 mg/5 mL, 200 mg/5 mL, 250 mg/5 mL, 400 mg/5 mL). Administration: May be taken with or without food. Take at evenly spaced intervals to maintain consistent blood levels. Capsules should be swallowed whole. Chewable tablets must be chewed or crushed before swallowing. Oral suspension: Shake well before each use; refrigerate reconstituted suspension; discard unused portion after 14 days. Storage: Capsules/tablets at 20–25°C (68–77°F). Reconstituted suspension: refrigerate at 2–8°C.',
4),
(5, 'Initial: 5 mg orally once daily. Max: 10 mg once daily.', 'Age 6-17 years: 2.5-5 mg once daily.', 'No dose adjustment required.', 'Initial: 2.5 mg once daily for hypertension; titrate slowly.',
'OVERDOSE — Signs & Symptoms: Excessive peripheral vasodilation leading to marked and potentially prolonged systemic hypotension, reflex tachycardia. Severe hypotension can progress to shock. In massive overdose, non-cardiogenic pulmonary edema may develop 12-24 hours after ingestion. Severity: Potentially fatal from cardiovascular collapse, especially in combination with other antihypertensives. Management: IV calcium gluconate (10%) to reverse calcium channel blockade. IV fluids and vasopressors (norepinephrine) for hypotension. High-dose insulin-euglycemia therapy for refractory shock. Activated charcoal if within 1-2 hours. Hemodialysis is not effective due to high protein binding (~97.5%).',
'UNDERDOSE / MISSED DOSE — Effects: Inadequate blood pressure control; sustained untreated hypertension damages target organs (heart, kidneys, brain, retina). For chronic stable angina, subtherapeutic doses result in recurrent anginal episodes and reduced exercise tolerance. Recommended range: 5–10 mg/day for most adults. Missed dose: Take as soon as remembered; do not double the dose. Severity: Non-acutely dangerous but abrupt discontinuation after chronic use may not cause rebound hypertension (unlike beta-blockers), though BP will return to untreated levels.',
'Route: Oral. Available forms: Tablets (2.5 mg, 5 mg, 10 mg); oral suspension may be compounded. Administration: May be taken with or without food. Administer once daily. Tablets may be crushed and mixed with water or applesauce for patients with difficulty swallowing. Storage: Store at 15–30°C (59–86°F). Protect from light and moisture. Dispense in tight, light-resistant container.',
6);

-- 5. Safety warnings
INSERT INTO safety_warnings (drug_id, contraindications, black_box_warnings, pregnancy_risk, lactation_risk, source_id) VALUES
(1, 'Hypersensitivity to metformin. Severe renal impairment (eGFR <30). Acute or chronic metabolic acidosis, including diabetic ketoacidosis.', 'Lactic acidosis: Rare but serious. Risk increases with renal impairment, hepatic impairment, excessive alcohol intake, and conditions associated with hypoxia.', 'Category B – Generally considered acceptable based on available data. ACOG supports use.', 'Present in breast milk in small amounts. Generally considered compatible with breastfeeding.', 1),
(2, 'Hypersensitivity to lisinopril or other ACE inhibitors. History of angioedema. Concomitant use with aliskiren in patients with diabetes. Co-administration with or within 36 hours of neprilysin inhibitors (e.g., sacubitril).', 'Pregnancy: Drugs that act on the renin-angiotensin system can cause injury and death to the developing fetus. Discontinue as soon as pregnancy is detected.', 'Category D – Evidence of human fetal risk. Contraindicated in pregnancy.', 'Unknown if excreted in breast milk. Not recommended during breastfeeding.', 2),
(3, 'Hypersensitivity to atorvastatin or any excipient. Active liver disease or unexplained persistent elevations of serum transaminases. Pregnancy and lactation.', 'No boxed warning. Monitor hepatic function prior to and during treatment.', 'Category X – Contraindicated in pregnancy. Cholesterol biosynthesis inhibition may cause fetal harm.', 'Contraindicated during lactation. Unknown if excreted in breast milk.', 3),
(4, 'Hypersensitivity to amoxicillin, penicillin, or any beta-lactam antibiotic.', 'No boxed warning. Serious and occasionally fatal hypersensitivity (anaphylactic) reactions reported.', 'Category B – Generally considered safe. Widely used in pregnancy.', 'Excreted in breast milk in small amounts. Compatible with breastfeeding with monitoring for infant sensitization.', 4),
(5, 'Hypersensitivity to amlodipine or other dihydropyridine calcium channel blockers.', 'No boxed warning.', 'Category C – Animal studies show adverse effects; no adequate human studies. Use only if benefit justifies risk.', 'Present in breast milk. Consider risk-benefit before use.', 6);

-- 6. Drug interactions
INSERT INTO drug_interactions (drug_id, interacting_drug, severity, description, source_id) VALUES
(1, 'Alcohol', 'major', 'Excessive alcohol intake potentiates the effect of metformin on lactate metabolism, increasing risk of lactic acidosis.', 8),
(1, 'Iodinated contrast agents', 'major', 'Acute renal failure may occur after intravascular iodinated contrast. Withhold metformin at time of or before procedure; restart 48 hours after if renal function is stable.', 8),
(2, 'Potassium supplements / K+-sparing diuretics', 'major', 'ACE inhibitors can increase serum potassium. Concomitant use with potassium supplements or potassium-sparing diuretics may lead to hyperkalemia.', 8),
(2, 'NSAIDs', 'moderate', 'NSAIDs may reduce the antihypertensive effect of ACE inhibitors and increase risk of renal impairment.', 8),
(3, 'Gemfibrozil / Fibrates', 'major', 'Increased risk of myopathy and rhabdomyolysis when statins are combined with fibrates.', 8),
(3, 'Grapefruit juice (large quantities)', 'moderate', 'CYP3A4 inhibition by grapefruit may increase atorvastatin levels.', 8),
(3, 'Cyclosporine', 'major', 'Significantly increases atorvastatin exposure. Avoid combination or limit atorvastatin to 10 mg/day.', 8),
(4, 'Methotrexate', 'major', 'Amoxicillin may reduce renal clearance of methotrexate, increasing toxicity risk.', 8),
(4, 'Warfarin', 'moderate', 'Amoxicillin may enhance anticoagulant effect; monitor INR closely.', 8),
(5, 'Simvastatin', 'moderate', 'Amlodipine increases simvastatin exposure. Limit simvastatin to 20 mg/day when co-administered.', 8),
(5, 'Cyclosporine', 'moderate', 'Amlodipine may increase cyclosporine levels. Monitor cyclosporine levels.', 8),
(2, 'Lisinopril + Metformin', 'minor', 'ACE inhibitors may enhance the hypoglycemic effect of antidiabetic agents. Monitor blood glucose.', 8);

-- 7. Pricing (approximate US prices)
INSERT INTO pricing (drug_id, approximate_cost, generic_available, source_id) VALUES
(1, '$4 – $30/month (generic)', TRUE, 7),
(2, '$3 – $20/month (generic)', TRUE, 7),
(3, '$6 – $30/month (generic); $200+ for brand', TRUE, 7),
(4, '$4 – $25/month (generic)', TRUE, 7),
(5, '$4 – $20/month (generic)', TRUE, 7);

-- 8. Reimbursement
INSERT INTO reimbursement (drug_id, scheme_name, coverage_notes, source_id) VALUES
(1, 'Medicare Part D', 'Covered under most Part D formularies as Tier 1 (preferred generic).', 7),
(1, 'Medicaid', 'Covered in all state Medicaid programs.', 7),
(2, 'Medicare Part D', 'Covered under most Part D formularies as Tier 1 (preferred generic).', 7),
(3, 'Medicare Part D', 'Generic covered as Tier 1-2. Brand Lipitor may require prior authorization.', 7),
(4, 'Medicare Part D', 'Covered under most Part D formularies as Tier 1.', 7),
(5, 'Medicare Part D', 'Generic covered as Tier 1. Widely available.', 7);

SELECT 'Seed data loaded successfully.' AS status;
