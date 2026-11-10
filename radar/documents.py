import io, re, zipfile, hashlib, html
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import os
from pypdf import PdfReader
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pathlib import Path
fontdir=Path(__file__).parent/"assets"
pdfmetrics.registerFont(TTFont("RadarSans",str(fontdir/"DejaVuSans.ttf")))
pdfmetrics.registerFont(TTFont("RadarSansBold",str(fontdir/"DejaVuSans-Bold.ttf")))

MAX_SIZE=8*1024*1024
SKILLS=['Active Directory','Entra ID','Microsoft 365','Office 365','Exchange','Intune','SCCM','Tanium','PowerShell','Windows','Linux','Ubuntu','DNS','DHCP','TCP/IP','VPN','Hyper-V','Proxmox','Docker','Azure','AWS','help desk','service desk','desktop support','technical support','network troubleshooting','IT support','hardware','Epic','ConnectWise','customer service','ticketing','ITIL','SQL','Python','VMware','SharePoint','Group Policy','GPO','security','backup','S3','troubleshooting','CompTIA A+','Security+']

def extract(name,data):
    ext=name.rsplit('.',1)[-1].lower()
    if len(data)>MAX_SIZE:raise ValueError('Maximum file size is 8 MB.')
    if ext=='txt':text=data.decode('utf-8-sig')
    elif ext=='docx':
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            if len(z.infolist())>1000 or sum(x.file_size for x in z.infolist())>25*1024*1024:raise ValueError('DOCX content exceeds the document limit.')
            if any('vbaProject' in x.filename for x in z.infolist()):raise ValueError('Macro-enabled files are not supported.')
        d=Document(io.BytesIO(data));parts=[]
        for child in d.element.body:
            if child.tag==qn('w:p'):
                from docx.text.paragraph import Paragraph as P
                para=P(child,d)
                bullet=para.style.name.startswith('List') or (para._p.pPr is not None and para._p.pPr.numPr is not None)
                parts.append(('- ' if bullet else '')+para.text)
            elif child.tag==qn('w:tbl'):
                from docx.table import Table
                parts.extend(' | '.join(c.text for c in row.cells) for row in Table(child,d).rows)
        text='\n'.join(parts)
    elif ext=='pdf':
        reader=PdfReader(io.BytesIO(data))
        if reader.is_encrypted:raise ValueError('Upload an unlocked document.')
        if len(reader.pages)>50:raise ValueError('Documents are limited to 50 pages.')
        text='\n'.join(p.extract_text() or '' for p in reader.pages)
    else:raise ValueError('Upload a PDF, DOCX, or UTF-8 TXT file.')
    text=text.replace('\x00','').strip()
    if len(text)<30:raise ValueError('No readable text found. For scanned PDFs, upload a DOCX or text version.')
    if len(text)>150000:raise ValueError('Extracted text exceeds the document limit.')
    return text

def words(s):return set(re.findall(r'[a-z0-9+#]+',s.lower()))
def has_phrase(phrase,text):return bool(re.search(r'(?<![\w])'+re.escape(phrase)+r'(?![\w])',text,re.I))
def analyze(resume,description):
    required=[s for s in SKILLS if has_phrase(s,description)]
    matched=[s for s in required if has_phrase(s,resume)]
    missing=[s for s in required if s not in matched]
    return {'matched':matched,'missing':missing,'coverage':round(len(matched)/len(required)*100) if required else None,'label':'Keyword coverage only; not an ATS pass score'}

def reorder_bullets(lines,job):
    """Reorder only adjacent existing bullets, never employer/date/section headings."""
    out=[];block=[];wanted=words(job)
    def flush():
        if block:out.extend(sorted(block,key=lambda x:len(words(x)&wanted),reverse=True));block.clear()
    for line in lines:
        if re.match(r'^\s*[-•*]\s+',line):block.append(line)
        else:flush();out.append(line)
    flush();return out

def prepare_resume(original,job):
    report=analyze(original,job['description']);lines=reorder_bullets(original.splitlines(),job['description'])
    # Preserve all facts. Add only an explicitly labeled target and verified keywords.
    insertion=next((i for i,s in enumerate(lines[1:5],1) if not s.strip()),min(2,len(lines)))
    additions=['',f"Target position: {job['title']} at {job['company']}"]
    if report['matched']:additions.append('Relevant skills: '+', '.join(report['matched']))
    result='\n'.join(lines[:insertion]+additions+['']+lines[insertion:])
    return result,report

def evidence(resume,description):
    target=words(description);lines=[s.strip().lstrip('-•* ') for s in resume.splitlines() if 45<len(s.strip())<400]
    # Use verbatim achievement/experience lines; exclude contact details and headings.
    scored=[(len(words(s)&target),s) for s in lines if not re.search(r'@|https?://|\b\d{3}[-.) ]\d{3}',s)]
    return [s for score,s in sorted(scored,key=lambda x:x[0],reverse=True) if score>1][:3]

def cover_letter(resume,base,job,profile):
    report=analyze(resume,job['description']);proof=evidence(resume,job['description'])
    values={'company':job['company'],'role':job['title'],'name':profile.get('name',''),'relevant_skills':', '.join(report['matched']) or 'the experience described in my resume','evidence':'\n'.join('- '+x for x in proof)}
    if '{{company}}' in base and '{{role}}' in base:
        text=base
        for k,v in values.items():text=text.replace('{{'+k+'}}',v)
        if re.search(r'{{[^}]+}}',text):raise ValueError('The cover-letter template contains unsupported placeholders.')
        mode='Your cover-letter template with job-specific replacements'
    else:
        opening=f"I am applying for the {job['title']} position at {job['company']}."
        body='My background includes '+', '.join(report['matched'][:7])+'.' if report['matched'] else 'I would welcome a conversation about how my experience relates to this role.'
        examples='\n\nRelevant examples from my experience:\n'+'\n'.join('- '+x for x in proof) if proof else ''
        text=f"{profile.get('name','')}\n{profile.get('email','')}\n{profile.get('location','')}\n\nDear Hiring Team,\n\n{opening} {body}{examples}\n\nThank you for considering my application. I would appreciate the opportunity to discuss the position and learn more about your team.\n\nSincerely,\n{profile.get('name','')}"
        mode='Evidence-based draft; original cover letter kept as reference. Add {{company}} and {{role}} to a template to reuse your own wording.'
    return text,mode

def followup(job,profile,applied,contact='Hiring Team'):
    when=datetime.fromtimestamp(applied,ZoneInfo(os.getenv("RADAR_TIMEZONE","America/Chicago"))).strftime('%B %d, %Y') if applied else 'recently'
    return f"Subject: Following up on my application for {job['title']}\n\nHello {contact},\n\nI applied for the {job['title']} position at {job['company']} on {when} and wanted to follow up. I remain interested in the opportunity and would appreciate any update you can share about the hiring timeline.\n\nPlease let me know if I can provide any additional information. Thank you for your time and consideration.\n\nBest regards,\n{profile.get('name','')}"

def docx_bytes(text):
    d=Document()
    for style in d.styles:
        for border in list(style.element.iter(qn('w:pBdr'))):border.getparent().remove(border)
    sec=d.sections[0];sec.top_margin=sec.bottom_margin=Inches(.65);sec.left_margin=sec.right_margin=Inches(.7)
    style=d.styles['Normal'];style.font.name='Calibri';style.font.size=Pt(10.5);style.font.color.rgb=RGBColor(0,0,0);style.paragraph_format.space_after=Pt(5)
    for n,line in enumerate(text.splitlines()):
        line=line.strip()
        if not line:continue
        p=d.add_paragraph();p.paragraph_format.widow_control=True
        if n==0:p.style=d.styles['Title'];p.style.font.color.rgb=RGBColor(0,0,0);p.style.font.name='Calibri';p.style.font.size=Pt(17)
        if re.match(r'^[-•*]\s+',line):p.style='List Bullet';line=re.sub(r'^[-•*]\s+','',line)
        r=p.add_run(line)
        if n>0 and len(line)<65 and (line.isupper() or line.rstrip(':').lower() in ['experience','education','skills','certifications','professional experience','summary']):r.bold=True;p.paragraph_format.keep_with_next=True
    d.core_properties.author='';d.core_properties.last_modified_by=''
    b=io.BytesIO();d.save(b);return b.getvalue()

def pdf_bytes(text):
    b=io.BytesIO();styles=getSampleStyleSheet();story=[]
    styles['Title'].fontName='RadarSansBold';styles['Title'].fontSize=17;styles['Title'].leading=22;styles['Title'].alignment=0
    styles['BodyText'].fontName='RadarSans';styles['BodyText'].fontSize=10;styles['BodyText'].leading=14
    for i,line in enumerate(text.splitlines()):
        if not line.strip():story.append(Spacer(1,7));continue
        story.append(Paragraph(html.escape(line),styles['Title'] if i==0 else styles['BodyText']))
    SimpleDocTemplate(b,pagesize=(612,792),leftMargin=50,rightMargin=50,topMargin=45,bottomMargin=45).build(story)
    return b.getvalue()
