# -*- coding: utf-8 -*-
# Copyright (c) 2017-2018, libracore (https://www.libracore.com) and contributors
# License: AGPL v3. See LICENCE

from __future__ import unicode_literals
import frappe
from frappe import throw, _
from collections import defaultdict
import time
#from erpnextswiss.erpnextswiss.common_functions import get_building_number, get_street_name, get_pincode, get_city
import html              # used to escape xml content

@frappe.whitelist()
def get_payments(payment_type):
    payments = frappe.db.sql(""" Select pe.name, pe.posting_date, pe.paid_amount, pe.party, pe.party_name, pe.paid_from, pe.paid_to_account_currency, per.reference_doctype , 
                                per.reference_name
                            From `tabPayment Entry` as pe 
                            Left Join `tabPayment Entry Reference` as per ON per.parent = pe.name
                            Where pe.docstatus = 0 and pe.payment_type = "Pay" and pe.party_type = "Supplier" and pe.custom_xml_file_generated = 0
                            order by posting_date
                            """,as_dict = 1)

    merged_data = defaultdict(list)
    for row in payments:
        key = row['name']
        merged_data[key].append(row['reference_name'])
    
    sorted_data = {}
    for key, values in merged_data.items():
        sorted_data.update({key:values}) 
    
    sort_list = []
    data = []
    for row in payments:
        if sorted_data.get(row.name):
            row.update({"reference_name":sorted_data.get(row.name)})
        if row.name not in sort_list:
            sort_list.append(row.name)
            data.append(row)
            
    _payments = []
    
    for row in data:
        if payment_type == "Domestic (Swedish) Payments":
            if frappe.db.get_value("Supplier", row.party , 'plus_giro_number') or frappe.db.get_value("Supplier", row.party , 'bank_giro_number'):
                _payments.append(row)
        if payment_type == "SEPA":
            if frappe.db.get_value("Supplier", row.party , 'bank_bic') and frappe.db.get_value("Supplier", row.party , 'iban_code'):
                _payments.append(row)
    return { 'payments': _payments }

@frappe.whitelist()
def generate_payment_file(payments ,payment_export_settings , posting_date , payment_type):
    if payment_type == "SEPA":
        content = genrate_file_for_sepa(payments ,payment_export_settings , posting_date , payment_type)
        return { 'content': content, 'skipped': 0 }
    # creates a pain.001 payment file from the selected payments
    try:
        # convert JavaScript parameter into Python array
        payments = eval(payments)
        # remove empty items in case there should be any (bigfix for issue #2)
        payments = list(filter(None, payments))
        
        # array for skipped payments
        skipped = []
        
        # create xml header
        content = make_line("<?xml version=\"1.0\" encoding=\"UTF-8\"?>")
        # define xml template reference
        content += make_line("<Document xmlns=\"urn:iso:std:iso:20022:tech:xsd:pain.001.001.03\" xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\" xsi:schemaLocation=\"urn:iso:std:iso:20022:tech:xsd:pain.001.001.03 pain.001.001.03.xsd\">")
        # transaction holder
        content += make_line("  <CstmrCdtTrfInitn>")
        ### Group Header (GrpHdr, A-Level)
        # create group header
        content += make_line("    <GrpHdr>")
        # message ID (unique, SWIFT-characters only)
        content += make_line("      <MsgId>MSG-" + time.strftime("%Y%m%d%H%M%S") + "</MsgId>")
        # creation date and time ( e.g. 2010-02-15T07:30:00 )
        content += make_line("      <CreDtTm>" + time.strftime("%Y-%m-%dT%H:%M:%S") + "Z" + "</CreDtTm>")
        # number of transactions in the file
        transaction_count = 0
        transaction_count_identifier = "<!-- $COUNT -->"
        content += make_line("      <NbOfTxs>" + transaction_count_identifier + "</NbOfTxs>")
        # total amount of all transactions ( e.g. 15850.00 )  (sum of all amounts)
        control_sum = 0.0
        control_sum_identifier = "<!-- $CONTROL_SUM -->"
        content += make_line("      <CtrlSum>" + control_sum_identifier + "</CtrlSum>")
        # initiating party requires at least name or identification
        content += make_line("      <InitgPty>")
        # initiating party name ( e.g. MUSTER AG )
        content += make_line("        <Nm>" + get_company_name(payments[0]) + "</Nm>")
        content += make_line("        <Id>")                      
        content += make_line("        <OrgId>")
        content += make_line("        <Othr>")
        content += make_line("        <Id>556036867100</Id>")
        content += make_line("        <SchmeNm>")
        content += make_line("        <Cd>BANK</Cd>")
        content += make_line("        </SchmeNm>")
        content += make_line("        </Othr>")
        content += make_line("        </OrgId>")
        content += make_line("        </Id>")                                           
        content += make_line("      </InitgPty>")
        content += make_line("    </GrpHdr>")
        ### Payment Information (PmtInf, B-Level)
        # payment information records (1 .. 99'999)
        content += make_line("    <PmtInf>")
        # unique (in this file) identification for the payment ( e.g. PMTINF-01, PMTINF-PE-00005 )
        content += make_line("      <PmtInfId>" + payments[0] + "</PmtInfId>")
        content += make_line("      <PmtMtd>TRF</PmtMtd>")
        content += make_line("      <NbOfTxs>" + transaction_count_identifier + "</NbOfTxs>")
        content += make_line("      <CtrlSum>" + control_sum_identifier + "</CtrlSum>")
        content += make_line("      <PmtTpInf>")
        content += make_line("          <SvcLvl>")
        content += make_line("            <Prtry>MPNS</Prtry>")
        content += make_line("          </SvcLvl>")
        content += make_line("        </PmtTpInf>")
        required_execution_date = posting_date
        content += make_line("      <ReqdExctnDt>{0}</ReqdExctnDt>".format(required_execution_date))
        content += make_line("      <Dbtr>")
        company_name = frappe.db.get_value('Payment Export Settings',payment_export_settings,'company_name')
        content += make_line("      <Nm>{0}</Nm>".format(company_name))


        content += make_line("        <PstlAdr>")
        street_name = frappe.db.get_value('Payment Export Settings',payment_export_settings,'street_name')
        content += make_line("          <StrtNm>" + street_name + "</StrtNm>")
        post_code = frappe.db.get_value('Payment Export Settings',payment_export_settings,'post_code')
        content += make_line("          <PstCd>" + post_code + "</PstCd>")
        town_name = frappe.db.get_value('Payment Export Settings',payment_export_settings,'town_name')
        content += make_line("          <TwnNm>" + town_name + "</TwnNm>")
        country = frappe.db.get_value('Payment Export Settings',payment_export_settings,'country')
        content += make_line("          <Ctry>" + country + "</Ctry>")
        content += make_line("        </PstlAdr>")
        content += make_line("        <Id>")                      
        content += make_line("        <OrgId>")
        content += make_line("        <Othr>")
        content += make_line("        <Id>556036867100</Id>")
        content += make_line("        <SchmeNm>")
        content += make_line("        <Cd>BANK</Cd>")
        content += make_line("        </SchmeNm>")
        content += make_line("        </Othr>")
        content += make_line("        </OrgId>")
        content += make_line("        </Id>")                                           
        content += make_line("      </Dbtr>")  
        content += make_line("      <DbtrAcct>")
        content += make_line("        <Id>")  
        iban = frappe.db.get_value('Payment Export Settings',payment_export_settings,'iban_for_domestic_payment')
        content += make_line("          <IBAN>{0}</IBAN>".format(iban.replace(" ", "") ))        
        content += make_line("        </Id>")
        content += make_line("      </DbtrAcct>")

        content += make_line("      <DbtrAgt>")
        content += make_line("        <FinInstnId>")
        bic = frappe.db.get_value('Payment Export Settings',payment_export_settings,'bic')
        content += make_line("      <BIC>{0}</BIC>".format(bic))

        content += make_line("        <PstlAdr>")
        content += make_line("          <Ctry>" + country + "</Ctry>")        
        content += make_line("        </PstlAdr>")
        content += make_line("        </FinInstnId>")
        content += make_line("      </DbtrAgt>")

        for payment in payments:
            frappe.db.set_value("Payment Entry" , payment , "custom_xml_file_generated" , 1)
            payment_record = frappe.get_doc('Payment Entry', payment)
            workflow_state = frappe.db.get_value("Payment Export Setting",payment_export_settings , 'workflow_state')
            if workflow_state:
                frappe.db.set_value("Purchase Invoice" , payment_record.references[0].reference_name , 'workflow_state' , workflow_state , update_modified = False)
            payment_content = ""
            payment_content += make_line("      <CdtTrfTxInf>")
            payment_content += make_line("        <PmtId>")
            # instruction identification 
            payment_content += make_line("          <InstrId>INSTRID-" + payment + "</InstrId>")
            # end-to-end identification (should be used and unique within B-level; payment entry name)
            payment_content += make_line("          <EndToEndId>" + payment.replace('-',"") + "</EndToEndId>")
            payment_content += make_line("        </PmtId>")
            payment_content += make_line("        <Amt>")
            payment_content += make_line("          <InstdAmt Ccy=\"{0}\">{1:.2f}</InstdAmt>".format(
                payment_record.paid_from_account_currency,
                payment_record.paid_amount))
            payment_content += make_line("        </Amt>")
            chrgbr = frappe.db.get_value('Payment Export Settings',payment_export_settings,'chrgbr')
            payment_content += make_line("      <ChrgBr>{0}</ChrgBr>".format(chrgbr))
            payment_content += make_line("        <CdtrAgt>")
            payment_content += make_line("          <FinInstnId>")
            payment_content += make_line("          <ClrSysMmbId>")
            payment_content += make_line("          <ClrSysId>")
            cd = frappe.db.get_value('Payment Export Settings',payment_export_settings,'cd')
            payment_content += make_line("            <Cd>{0}</Cd>".format(cd))
            payment_content += make_line("          </ClrSysId>")
            supplier_bank_giro = frappe.db.get_value('Supplier', payment_record.party,'bank_giro_number')
            supplier_plush_giro = frappe.db.get_value("Supplier", payment_record.party , 'plus_giro_number')
            if supplier_bank_giro:
                cmmbidd = frappe.db.get_value('Payment Export Settings',payment_export_settings,'mmbid_for_bank_giro_number')
            if supplier_plush_giro:
                cmmbidd = frappe.db.get_value('Payment Export Settings',payment_export_settings,'mmbid_for_plus_giro_number')
            payment_content += make_line("            <MmbId>{0}</MmbId>".format(cmmbidd))
            payment_content += make_line("          </ClrSysMmbId>")
            payment_content += make_line("          </FinInstnId>")
            payment_content += make_line("        </CdtrAgt>")

            creditor_info = add_creditor_info(payment_record)
            if creditor_info:
                payment_content += creditor_info
            else:
                # no address found, skip entry (not valid)
                content += add_invalid_remark( _("{0}: no address (or country) found").format(payment) )
                skipped.append(payment)
                continue
            payment_content += make_line("        <CdtrAcct>")
            payment_content += make_line("          <Id>")
            payment_content += make_line("            <Othr>")
            supplier_bank_giro = frappe.db.get_value('Supplier', payment_record.party,'bank_giro_number')
            supplier_plus_giro = frappe.db.get_value('Supplier', payment_record.party,'plus_giro_number')
            if supplier_bank_giro:
                payment_content += make_line("              <Id>{0}</Id>".format(supplier_bank_giro.replace("-" , "") if supplier_bank_giro else '' ))
                payment_content += make_line("            <SchmeNm>")
                payment_content += make_line("                <Prtry>BGNR</Prtry>")
                payment_content += make_line("            </SchmeNm>")
            elif supplier_plus_giro:
                payment_content += make_line("              <Id>{0}</Id>".format(supplier_plus_giro.replace("-" , "") if supplier_plus_giro else '' ))
                payment_content += make_line("            <SchmeNm>")
                payment_content += make_line("                <cd>BBAN</cd>")
                payment_content += make_line("            </SchmeNm>")
            payment_content += make_line("            </Othr>")
            payment_content += make_line("          </Id>")
            payment_content += make_line("        </CdtrAcct>")
            payment_content += make_line("        <RmtInf>")
            for reference in payment_record.references:
                payment_content += make_line("        <Strd>")
                payment_content += make_line("        <RfrdDocInf>")
                payment_content += make_line("        <Tp>")
                payment_content += make_line("        <CdOrPrtry>")
                payment_content += make_line("        <Cd>CINV</Cd>")
                payment_content += make_line("        </CdOrPrtry>")
                payment_content += make_line("        </Tp>")
                if reference.reference_doctype in ["Purchase Invoice" , "Purchase Receipt"]:
                    bill_no = frappe.db.get_value(reference.reference_doctype , reference.reference_name , 'bill_no')
                if reference.reference_doctype == "Purchase Order":
                    bill_no = reference.reference_name
                payment_content += make_line("        <Nb>{0}</Nb>".format(bill_no))
                payment_content += make_line("        </RfrdDocInf>")
                payment_content += make_line("        <RfrdDocAmt>")
                payment_content += make_line("          <RmtdAmt Ccy=\"{0}\">{1:.2f}</RmtdAmt>".format(payment_record.paid_from_account_currency,reference.allocated_amount))
                payment_content += make_line("        </RfrdDocAmt>")
                payment_content += make_line("        </Strd>")
            payment_content += make_line("        </RmtInf>")

            payment_content += make_line("      </CdtTrfTxInf>")
            content += payment_content
            transaction_count += 1
            control_sum += payment_record.paid_amount

        content += make_line("    </PmtInf>")
        content += make_line("  </CstmrCdtTrfInitn>")
        content += make_line("</Document>")
        # insert control numbers
        content = content.replace(transaction_count_identifier, "{0}".format(transaction_count))
        content = content.replace(control_sum_identifier, "{:.2f}".format(control_sum))
        
        return { 'content': content, 'skipped': skipped }
    except IndexError:
        frappe.msgprint( _("Please select at least one payment."), _("Information") )
        return
    except:
        frappe.throw( _("Error while generating xml. Make sure that you made required customisations to the DocTypes.") )
        return

def add_creditor_info(payment_record):
    payment_content = ""
    # creditor information
    payment_content += make_line("        <Cdtr>") 
    # name of the creditor/supplier
    name = payment_record.party
    if payment_record.party_type == "Employee":
        name = frappe.get_value("Employee", payment_record.party, "employee_name")
    if payment_record.party_type == "Supplier":
        name = frappe.db.get_value("Supplier",name,"supplier_name")
    payment_content += make_line("          <Nm>" + name  + "</Nm>")
    # address of creditor/supplier (should contain at least country and first address line
    # get supplier address
    if payment_record.party_type == "Supplier" or payment_record.party_type == "Customer":
        supplier_address = get_billing_address(payment_record.party, payment_record.party_type)
        if supplier_address == None:
            return None
        street = get_street_name(supplier_address.address_line1)
        plz = supplier_address.pincode
        city = supplier_address.city 
        # country (has to be a two-digit code)
        try:
            country_code = frappe.get_value('Country', supplier_address.country, 'code').upper()
        except:
            country_code = "CH"
    elif payment_record.party_type == "Employee":
        employee = frappe.get_doc("Employee", payment_record.party)
        if employee.permanent_address:
           address = employee.permanent_address
        elif employee.current_address:
            address = employee.current_address
        else:
            # no address found
            return None
        try:
            lines = address.split("\n")
            street = "Street" #get_street_name(lines[0])
            building = "Building" #get_building_number(lines[0])
            plz = "PIN" #get_pincode(lines[1])
            city = "City" #get_city(lines[1])
            country_code = "CH"                
        except:
            # invalid address
            return None
    else:
        # unknown supplier type
        return None
    payment_content += make_line("          <PstlAdr>")
    # street name
    payment_content += make_line("            <StrtNm>" + street + "</StrtNm>")
    # postal code
    payment_content += make_line("            <PstCd>{0}</PstCd>".format(plz))
    # town name
    payment_content += make_line("            <TwnNm>" + city + "</TwnNm>")
    payment_content += make_line("            <Ctry>" + country_code + "</Ctry>")
    payment_content += make_line("            <AdrLine>" + street + "</AdrLine>")
    payment_content += make_line("          </PstlAdr>")
    payment_content += make_line("        </Cdtr>") 
    return payment_content
            
def get_total_amount(payments):
    # get total amount from all payments
    total_amount = float(0)
    for payment in payments:
        payment_amount = frappe.get_value('Payment Entry', payment, 'paid_amount')
        total_amount += payment_amount
        
    return total_amount

def get_company_name(payment_entry):
    return frappe.get_value('Payment Entry', payment_entry, 'company')

# adds Windows-compatible line endings (to make the xml look nice)    
def make_line(line):
    return line + "\r\n"

# add a remark if a payment entry was skipped
def add_invalid_remark(remark):
    return make_line("    <!-- " + remark + " -->")
    
# try to find the optimal billing address
def get_billing_address(supplier_name, supplier_type="Supplier"):
    if supplier_type == "Customer":
        linked_addresses = frappe.get_all('Dynamic Link', 
        filters={
            'link_doctype': 'customer', 
            'link_name': supplier_name, 
            'parenttype': 'Address'
        }, 
        fields=['parent'])         
    else:
        linked_addresses = frappe.get_all('Dynamic Link', 
        filters={
            'link_doctype': 'supplier', 
            'link_name': supplier_name, 
            'parenttype': 'Address'
        }, 
        fields=['parent'])     
    if len(linked_addresses) > 0:
        if len(linked_addresses) > 1:
            for address_name in linked_addresses:
                address = frappe.get_doc('Address', address_name)            
                if address.address_type == "Billing":
                    # this is a billing address, keep as option
                    billing_address = address
                    if address.is_primary_address == 1:
                        # this is the primary billing address
                        return address
                if address.is_primary_address == 1:
                    # this is a primary but not billing address
                    primary_address = address
            # evaluate best address found
            if billing_address:
                # found one or more billing address (but no primary)
                return billing_address
            elif primary_address:
                # found no billing but a primary address
                return primary_address
            else:
                # found neither billing nor a primary address
                return frappe.get_doc('Address', linked_addresses[0].parent)
        else:
            # return the one (and only) address 
            return frappe.get_doc('Address', linked_addresses[0].parent)
    else:
        # no address found
        return None

def get_building_number(address_line):
    parts = address_line.strip().split(" ")
    if len(parts) > 1:
        return parts[-1]
    else:
        return ""

def get_street_name(address_line):
    parts = address_line.strip().split(" ")
    if len(parts) > 1:
        return " ".join(parts[:-1])
    else:
        return address_line

# get pincode from address line
def get_pincode(address_line):
    parts = address_line.strip().split(" ")
    if len(parts) > 1:
        return parts[0]
    else:
        return ""

# get city from address line
def get_city(address_line):
    parts = address_line.strip().split(" ")
    if len(parts) > 1:
        return " ".join(parts[1:])
    else:
        return address_line

# get primary address
# target types: Customer, Supplier, Company
@frappe.whitelist()
def get_primary_address(target_name, target_type="Customer"):
    sql_query = """SELECT 
            `tabAddress`.`address_line1`, 
            `tabAddress`.`address_line2`, 
            `tabAddress`.`pincode`, 
            `tabAddress`.`city`, 
            `tabAddress`.`county`,
            `tabAddress`.`country`, 
            UPPER(`tabCountry`.`code`) AS `country_code`, 
            `tabAddress`.`is_primary_address`
        FROM `tabDynamic Link` 
        LEFT JOIN `tabAddress` ON `tabDynamic Link`.`parent` = `tabAddress`.`name`
        LEFT JOIN `tabCountry` ON `tabAddress`.`country` = `tabCountry`.`name`
        WHERE `link_doctype` = '{type}' AND `link_name` = '{name}'
        ORDER BY `tabAddress`.`is_primary_address` DESC
        LIMIT 1;""".format(type=target_type, name=target_name)
    try:
        return frappe.db.sql(sql_query, as_dict=True)[0]
    except:
        return None

def genrate_file_for_sepa( payments ,payment_export_settings , posting_date , payment_type):
    payments = eval(payments)
    # remove empty items in case there should be any (bigfix for issue #2)
    payments = list(filter(None, payments))
    content = make_line("<?xml version='1.0' encoding='UTF-8'?>")
    content += make_line("<!-- SEB ISO 20022 V03 MIG, 6.1 SEPA CT IBAN ONLY -->")
    content += make_line("<Document xmlns='urn:iso:std:iso:20022:tech:xsd:pain.001.001.03' xmlns:xsi='http://www.w3.org/2001/XMLSchema-instance'>")
    content += make_line("  <CstmrCdtTrfInitn>")
    content += make_line("      <GrpHdr>")
    content += make_line("          <MsgId>{0}</MsgId>".format(time.strftime("%Y%m%d%H%M%S")))
    content += make_line("          <CreDtTm>{0}</CreDtTm>".format(time.strftime("%Y-%m-%dT%H:%M:%S")))
    transaction_count = 0
    transaction_count_identifier = "<!-- $COUNT -->"
    content += make_line("          <NbOfTxs>{0}</NbOfTxs>".format(transaction_count_identifier))
    control_sum = 0.0
    control_sum_identifier = "<!-- $CONTROL_SUM -->"
    content += make_line("          <CtrlSum>{0}</CtrlSum>".format(control_sum_identifier))
    content += make_line("          <InitgPty>")
    content += make_line("              <Nm>{0}</Nm>".format(get_company_name(payments[0])))
    content += make_line("              <Id>")
    content += make_line("                  <OrgId>")
    content += make_line("                      <Othr>")
    content += make_line("                          <Id>556036867100</Id>")
    content += make_line("                          <SchmeNm>")
    content += make_line("                              <Cd>BANK</Cd>")
    content += make_line("                          </SchmeNm>")
    content += make_line("                      </Othr>")
    content += make_line("                  </OrgId>")
    content += make_line("              </Id>")
    content += make_line("          </InitgPty>")
    content += make_line("      </GrpHdr>")
    content += make_line("      <PmtInf>")
    content += make_line("          <PmtInfId>{0}</PmtInfId>".format(payments[0]))
    content += make_line("          <PmtMtd>TRF</PmtMtd>")
    content += make_line("          <BtchBookg>false</BtchBookg>")
    content += make_line("          <NbOfTxs>{0}</NbOfTxs>".format(transaction_count_identifier))
    
    content += make_line("          <CtrlSum>{0}</CtrlSum>".format(control_sum_identifier))
    content += make_line("          <PmtTpInf>")
    content += make_line("              <SvcLvl>")
    content += make_line("                  <Cd>SEPA</Cd>")
    content += make_line("              </SvcLvl>")
    content += make_line("          </PmtTpInf>")
    required_execution_date = posting_date
    content += make_line("          <ReqdExctnDt>{0}</ReqdExctnDt>".format(required_execution_date))
    content += make_line("          <Dbtr>")
    company_name = frappe.db.get_value('Payment Export Settings',payment_export_settings,'company_name')
    content += make_line("              <Nm>{0}</Nm>".format(company_name))
    content += make_line("              <Id>")
    content += make_line("                  <OrgId>")
    content += make_line("                      <Othr>")
    content += make_line("                          <Id>55667755110004</Id>")
    content += make_line("                          <SchmeNm>")
    content += make_line("                              <Cd>BANK</Cd>")
    content += make_line("                          </SchmeNm>")
    content += make_line("                      </Othr>")
    content += make_line("                  </OrgId>")
    content += make_line("              </Id>")
    content += make_line("              <CtryOfRes>SE</CtryOfRes>")
    content += make_line("          </Dbtr>")
    content += make_line("          <DbtrAcct>")
    content += make_line("              <Id>")
    iban = frappe.db.get_value('Payment Export Settings',payment_export_settings,'iban_for_sepa_payment')
    content += make_line("                  <IBAN>{0}</IBAN>".format(iban))
    content += make_line("              </Id>")
    content += make_line("              <Ccy>EUR</Ccy>")
    content += make_line("          </DbtrAcct>")
    content += make_line("          <DbtrAgt>")
    content += make_line("          <!-- Note: For IBAN only on Debtor side use Othr/Id: NOTPROVIDED - see below -->")
    content += make_line("              <FinInstnId>")
    content += make_line("                  <Othr>")
    content += make_line("                      <Id>NOTPROVIDED</Id>")
    content += make_line("                  </Othr>")
    content += make_line("              </FinInstnId>")
    content += make_line("          </DbtrAgt>")
    content += make_line("          <ChrgBr>SLEV</ChrgBr>")
    for payment in payments:
        frappe.db.set_value("Payment Entry" , payment , "custom_xml_file_generated" , 1)
        payment_record = frappe.get_doc('Payment Entry', payment)
        workflow_state = frappe.db.get_value("Payment Export Setting",payment_export_settings , 'workflow_state')
        if workflow_state:
            frappe.db.set_value("Purchase Invoice" , payment_record.references[0].reference_name , 'workflow_state' , workflow_state , update_modified = False)
        content += make_line("          <CdtTrfTxInf>")
        content += make_line("              <PmtId>")
        content += make_line("                  <InstrId>{}</InstrId>".format(payment))
        content += make_line("                  <EndToEndId>{}</EndToEndId>".format(payment.replace('-',"")))
        content += make_line("              </PmtId>")
        content += make_line("              <Amt>")
        content += make_line("                  <InstdAmt Ccy=\"{0}\">{1:.2f}</InstdAmt>".format(
                payment_record.paid_from_account_currency,
                payment_record.paid_amount))
        content += make_line("              </Amt>")
        content += make_line("              <!-- Note: Creditor Agent should not be used at all for IBAN only on Creditor side -->")
        content += make_line("              <Cdtr>")
        if payment_record.party_type == "Employee":
            name = frappe.get_value("Employee", payment_record.party, "employee_name")
        if payment_record.party_type == "Supplier":
            name = frappe.db.get_value("Supplier",payment_record.party,"supplier_name")
        content += make_line("                  <Nm>{0}</Nm>".format(name))
        content += make_line("              </Cdtr>")
        content += make_line("              <CdtrAcct>")
        content += make_line("                  <Id>")
        iban_code = frappe.db.get_value("Supplier" , payment_record.party , 'iban_code')
        content += make_line("                      <IBAN>{0}</IBAN>".format(iban_code or ""))
        content += make_line("                  </Id>")
        content += make_line("              </CdtrAcct>")
        content += make_line("              <RmtInf>")
        sup_invoice_no = frappe.db.get_value("Purchase Invoice" , payment_record.references[0].reference_name , 'bill_no')
        content += make_line("                  <Ustrd>{0}</Ustrd>".format(sup_invoice_no if sup_invoice_no else ""))
        content += make_line("              </RmtInf>")
        content += make_line("          </CdtTrfTxInf>")
        transaction_count += 1
        control_sum += payment_record.paid_amount
    content += make_line("      </PmtInf>")
    content += make_line("  </CstmrCdtTrfInitn>")
    content += make_line("</Document>")
    content = content.replace(transaction_count_identifier, "{0}".format(transaction_count))
    content = content.replace(control_sum_identifier, "{:.2f}".format(control_sum))
    
    return content
