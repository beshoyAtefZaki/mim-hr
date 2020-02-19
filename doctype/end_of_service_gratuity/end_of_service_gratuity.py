# -*- coding: utf-8 -*-
# Copyright (c) 2018, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import frappe
from frappe.model.document import Document
from dateutil.relativedelta import relativedelta
from frappe import _

class EndOfServiceGratuity(Document):
    pass

@frappe.whitelist()
def get_eos_reward(selected_emp=None, based_on_basic_salary=None):
    if selected_emp:
        date_of_joining, relieving_date, resignation_letter_date, gender, reason_for_resignation, marital_status_date = \
        frappe.db.sql("""
            select date_of_joining,relieving_date,resignation_letter_date,gender,reason_for_resignation,marital_status_date
            from tabEmployee where name = %(selected_emp)s ;
            """, {'selected_emp': selected_emp})[0]

        worked_years = relativedelta(relieving_date, date_of_joining).years
        worked_months = relativedelta(relieving_date, date_of_joining).months + worked_years * 12
        worked_days = relativedelta(relieving_date, date_of_joining).days
        total_worked_days = (relieving_date - date_of_joining).days
        duration_text = "{0} years and {1} months {2} days".format(worked_years, worked_months - worked_years * 12,
                                                                   worked_days)
        eos_reward = 0
        if based_on_basic_salary == "1":
            base_eos_sal = get_avg_of_basesal(selected_emp, date_of_joining, relieving_date)
            if not base_eos_sal:
                return frappe.msgprint("Employee have no active base salary")
        else:
            # base_eos_sal = frappe.db.get_value("Salary Slip", {"employee": selected_emp, "docstatus": "1"}, "gross_pay",
            #                                    order_by="-end_date")
            #
            latest_sal_struc = frappe.db.get_value("Salary Structure Assignment",
                                                   {"employee": selected_emp, "docstatus": "1"}, "salary_structure",
                                                   order_by="from_date desc ")
            if not latest_sal_struc:
                return frappe.msgprint("Employee have No active Salary Structure ")

            earnings = frappe.db.get_values("Salary Detail",
                                            {"parent": latest_sal_struc, "docstatus": "1", "parentfield": "earnings"},
                                            "*")
            base_eos_sal = calculate_gross_pay(earnings, selected_emp, latest_sal_struc)

        # base_eos_sal = base_eos_sal / 30.0

        month_base_eos_sal = base_eos_sal #* 30
        # تطبيق المادة رقم84
        if relieving_date and not resignation_letter_date:
            eos_reward = get_normal_eos_reward(worked_years, worked_months, worked_days, month_base_eos_sal,
                                               total_worked_days)

        # تطبيق المادة رقم85
        if relieving_date and resignation_letter_date:

            # استثناء مما ورد في المادة
            if gender == "Female":
                eos_reward = check_female_reason_for_resignation(reason_for_resignation, marital_status_date,
                                                                 relieving_date, total_worked_days, worked_years,
                                                                 worked_months, worked_days, month_base_eos_sal)
                if eos_reward:
                    return eos_reward, duration_text

            if reason_for_resignation == "Compelling Reasons":
                eos_reward = get_normal_eos_reward(worked_years, worked_months, worked_days, month_base_eos_sal,
                                                   total_worked_days)
                return round(eos_reward, 2), duration_text

            eos_reward = get_divided_eos_reward(total_worked_days, month_base_eos_sal)

        return round(eos_reward, 2), duration_text


def check_female_reason_for_resignation(reason_for_resignation, marital_status_date, relieving_date, total_worked_days,
                                        worked_years, worked_months, worked_days, month_base_eos_sal):
    eos_reward = 0
    if marital_status_date:
        # Reason for Resignation
        if reason_for_resignation == "Married":
            if relativedelta(relieving_date, marital_status_date).months <= 6:
                eos_reward = get_normal_eos_reward(worked_years, worked_months, worked_days, month_base_eos_sal,
                                                   total_worked_days)

        elif reason_for_resignation == "Have Baby":
            if relativedelta(relieving_date, marital_status_date).months <= 3:
                eos_reward = get_normal_eos_reward(worked_years, worked_months, worked_days, month_base_eos_sal,
                                                   total_worked_days)

        return round(eos_reward, 2)


def get_avg_of_basesal(selected_emp, date_of_joining, relieving_date):
    avg_base_pay = 0
    base_pay = frappe.db.sql(
        ("""
        SELECT base 
            FROM `tabSalary Structure Assignment` 
            WHERE employee = %(selected_emp)s
                and from_date >= %(date_of_joining)s  
                and from_date <= %(relieving_date)s 
                order by from_date;

    """), ({'selected_emp': selected_emp, 'date_of_joining': date_of_joining, 'relieving_date': relieving_date}),
        as_list=True)
    if base_pay:
        base_pay_list = [x[0] for x in base_pay]
        if base_pay_list:
            avg_base_pay = sum(base_pay_list) / float(len(base_pay_list))

    return avg_base_pay


def get_normal_eos_reward(worked_years, worked_months, worked_days, month_base_eos_sal, total_worked_days):
    eos_reward = 0
    min_years_of_service = int(frappe.db.get_single_value('HR Settings', 'min_years_of_service'))
    per_of_first_five_years = int(frappe.db.get_single_value('HR Settings', 'days_of_first_five_years')) / 30.0
    per_after_five_years = int(frappe.db.get_single_value('HR Settings', 'days_after_five_years')) / 30.0
    if worked_years >= min_years_of_service:
        service_duration_in_years = worked_years + ((worked_months / 12.0 - worked_years)) + (worked_days / (30.0 * 12))
        if total_worked_days <= 5 * 12 * 30:
            eos_reward = per_of_first_five_years * service_duration_in_years * month_base_eos_sal
        elif total_worked_days > 5 * 12 * 30:
            rest_of_service_duration_in_years = (worked_years - 5) + ((worked_months / 12.0 - worked_years)) + (
                    worked_days / (30.0 * 12))
            eos_reward_after_five_years = per_after_five_years * rest_of_service_duration_in_years * month_base_eos_sal
            eos_reward_for_five_years = per_of_first_five_years * 5 * month_base_eos_sal
            eos_reward = eos_reward_for_five_years + eos_reward_after_five_years

    return eos_reward

def get_divided_eos_reward(total_worked_days, month_base_eos_sal):
    eos_reward = 0

    p1 = float(frappe.db.get_single_value('HR Settings', 'p1'))
    p2 = float(frappe.db.get_single_value('HR Settings', 'p2'))
    p3 = float(frappe.db.get_single_value('HR Settings', 'p3'))

    total_worked_months = total_worked_days / 30.0

    if (total_worked_months <= 22.99):
        eos_reward = 0
    elif (total_worked_months <= 59.99):
        eos_reward = (month_base_eos_sal / 23 * total_worked_months) * p1
    elif (total_worked_months <= 119.99):
        eos_reward = (month_base_eos_sal / 23 * 60 + (total_worked_months - 60) * month_base_eos_sal / 11) * p2
    elif (total_worked_months >= 120):
        eos_reward = (month_base_eos_sal / 23 * 60 + (total_worked_months - 60) * month_base_eos_sal / 11) * p3

    return eos_reward


def calculate_gross_pay(earnings, selected_emp, salary_structure):
    full_amount = 0
    data = get_data_for_eval(selected_emp, salary_structure)
    for struct_row in earnings:

        if not (struct_row.statistical_component or struct_row.amount_based_on_func):
            eval_amount = eval_full_condition_and_formula(struct_row, data)
            full_amount += eval_amount

    return full_amount


def get_data_for_eval(selected_emp, salary_structure):
    '''Returns data for evaluating formula'''
    data = frappe._dict()

    data.update(frappe.get_doc("Salary Structure Assignment",
                               {"employee": selected_emp, "salary_structure": salary_structure}).as_dict())
    data.update(frappe.get_doc("Employee", selected_emp).as_dict())

    return data


def eval_full_condition_and_formula(d, data):
    try:
        condition = d.condition.strip() if d.condition else None
        if condition:
            if not frappe.safe_eval(condition, None, data):
                return None

        amount = d.amount

        if d.amount_based_on_formula:
            formula = d.formula.strip() if d.formula else None
            if formula:
                amount = frappe.safe_eval(formula, None, data)

        if amount:
            data[d.abbr] = amount

        return amount

    except NameError as err:
        frappe.throw(_("Name error: {0}".format(err)))
    except SyntaxError as err:
        frappe.throw(
            _("Syntax error in formula or condition: {0}".format(err)))
    except Exception as e:
        frappe.throw(_("Error in formula or condition: {0}".format(e)))
        raise
