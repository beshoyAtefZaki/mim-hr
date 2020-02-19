from __future__ import unicode_literals
from frappe import _

def get_data():
	return {
		'heatmap': True,
		'heatmap_message': _('This is for Residence Data Renewal Transactions'),
		'fieldname': 'party',
		'transactions': [
			{
				'label': _('Journal Entry'),
				'items': ['Journal Entry']
			}
		]
	}