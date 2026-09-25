SECTORS = ['Climate & materials', 'Life sciences', 'Software & AI', 'Hardware & energy', 'Other']
SIGNAL_TYPES = ['technology_license', 'research_collaboration', 'industrial_partnership',
                'accelerator_participation', 'program_selection', 'award',
                'investor_affiliation', 'independent_coverage', 'community_activity']


def obj(properties):
    return {'type': 'object', 'properties': properties, 'required': list(properties),
            'additionalProperties': False}


def string(**kwargs):
    return {'type': 'string', **kwargs}


def array(items, maximum=12):
    return {'type': 'array', 'items': items, 'maxItems': maximum}


EVIDENCE = obj({'source_id': string(), 'quote': string()})
DISCOVERY = obj({'candidates': array(obj({
    'name': string(), 'aliases': array(string(), 4),
    'sector': string(enum=SECTORS), 'source_id': string(), 'quote': string(),
}), 7)})
ASSESSMENT = obj({
    'name': string(), 'official_domain': string(), 'sector': string(enum=SECTORS),
    'description': string(),
    'nj_presence': obj({
        'status': string(enum=['headquarters', 'operations', 'ecosystem_only', 'unclear', 'outside_nj', 'conflicting']),
        'location': string(), 'evidence': array(EVIDENCE, 4),
    }),
    'signals': array(obj({
        'type': string(enum=SIGNAL_TYPES), 'organization': string(), 'statement': string(),
        'event_date': string(description='YYYY, YYYY-MM, YYYY-MM-DD, or empty if not established by the quotation.'),
        'event_key': string(description='Same short event label for syndicated/repeated versions of one event.'),
        'status': string(enum=['current', 'historical', 'announced', 'unknown']),
        'source_role': string(enum=['institution_confirmation', 'independent_reporting', 'company_claim', 'directory']),
        'source_id': string(), 'quote': string(),
    }), 10),
    'uncertainties': array(string(), 6),
    'follow_up_query': string(description='One useful short company-specific query for an important evidence gap; empty if none.'),
})

DISCOVERY_INSTRUCTION = '''Find candidate startups for New Jersey Reputation & Ecosystem Interest.
Use only full source text. Pick actual named young companies with an NJ connection
and specific ecosystem evidence. Exclude government bodies, universities, investors,
publicly traded corporations and established large enterprises as candidates.
Prefer concrete partnerships, research activity or program participation. Diversify
sectors where sources support it. Return up to the requested count, no invented
padding. Quote a passage containing each company's name. Do not treat a cohort
location as every company's headquarters. Return aliases only if sources establish them.'''

ASSESSMENT_INSTRUCTION = '''Assess ONE supplied company for Reputation & Ecosystem Interest.
Use only the supplied full pages, never search snippets or model memory as evidence.
Match the right entity. NJ program membership alone is ecosystem_only, not NJ
headquarters or operations. Conflicting geographic information is conflicting.
Every evidence quote, including NJ evidence, MUST contain the company's name or
an established alias. Include adjacent sentences verbatim when needed to capture
the attribution. A name elsewhere on the page is not sufficient.
Copy quotes character for character, including Markdown links, punctuation and
whitespace. Do not paraphrase or tidy the source text inside quotations. If a
prior_assessment is supplied, retain its supported signals unless new evidence
actually contradicts them. Return the full updated assessment, not just new facts.
Mark only actual NJ operations/headquarters as supported, with literal quotations.
Extract specific named external relationships, recognition, coverage and community
activity. Distinguish actual collaboration from proposals, planned pilots and mere
logos. Attendance is not a university partnership. Accelerator acceptance does not
prove graduation or company success. Investors, universities and program operators
are interested parties: institution_confirmation is not independent_reporting.
Government grants and SBIR/STTR awards are program_selection, NEVER investor_affiliation.
A research proposal abstract does not itself prove that an award was received or
that work was performed. Old reporting supports historical activity, not an
assertion that a relationship is still current today.
An article republishing a startup press release is company_claim even on another
website; a counterparty explicitly confirming its own relationship can be
institution_confirmation, but keep the same event_key for the shared announcement.
HAX and SOSV are one family. NJEDA and CSIT are one family. Rutgers pages are one
family. Do not multiply an event because several websites publish it.
Use exact unmodified quotes, including punctuation and whitespace, from source text.
Quotes must support the statement and attribution, not just include a company name.
Event dates need explicit dated evidence; publication dates are separate metadata.
Do not infer that an old relationship is current. Do not evaluate funding amounts,
revenue, headcount, founder quality or business success. Never invent public-interest
growth. official_domain must match a retrieved company page; use empty otherwise.
Identify consequential unknowns. Suggest one short follow-up query only if it could
resolve a material gap. A useful result can have incomplete evidence. Keep prose concise.'''
