#!python3
# vim: ts=4 sw=4 noet

# A script to prepare emails for Guest Collections that will be auto-deleted
# immediately once auto-deleation is enabled.
# A. Karl Kornel, akkornel@stanford.edu, 2026-11
# © 2026 The Board of Trustees of the Leland Stanford Junior University

# An example of how to run the script:
# uv run email_expiring_guest_collections.py \
#     --cutoff-days 379 \
#     templates outputs ENDPOINT_UUID [COLLECTION_UUID]

# By default, the script will run on all Collections of an Endpoint.  To only
# run on one Collection, provide that Collection's UUID.  You must have at
# least the Activity Manager Role, either on the specific Collection, or on the
# entire Endpoint.

# Set cutoff-days to your planned auto_delete_timeout, plus the amount of
# notice you plan to give.  For example, if you plan an auto_delete_timeout of
# 1 year, and want to warn people 2 weeks in advnace, use a cutoff-days of
# 379 (that is, 365 + 14).

# templates is the directory where our Jinja2 templates live.  You must provide
# two templates:
# * subject.jinja2: A one-line template, used for the message subject.
# * message.jinja2: The message body.

# outputs is an empty directory.  Each Guest Collection will write three files:
# * UUID-recipients.txt: Email addresses of recipients, one address per line.
# * UUID-subject.txt: Email subject line
# * UUID.message: Email message body
# It's up to you to take those files and actually send the emails.

# Your message-body template can make plain text, HTML, whatever you want.
# You get four template variables:
# * collection: A GCS Collection document for the Guest Collection, as a Python
#   dict.
# * parent: A GCS Collection document for the parent Mapped Collection.
# * earliest_last_access: When the Endpoint started tracking last-accessed, as
#   a Python datetime.date.  If `collection.last_access` is None, use this.
# * days_since_last_activity: Pre-calculated `now - collection.last_access + 1`
#   (accounting that collection.last_access might be None)

# For Collection document schemas, see
# https://docs.globus.org/globus-connect-server/v5.4/api/openapi_schemas/:
# To figure out which Collection-schema version your GCS uses, check the
# Changelog at https://docs.globus.org/globus-connect-server/v5.4/api/
# For example, GCS version 5.4.82 used Schema collection#1.13.0
# NOTE: Your template variables will *not* include private fields!

#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "globus-sdk >=4.10",
#   "Jinja2",
# ]
# ///

# Start with stdlib packages
import argparse
import datetime
import email.message
import os
import pathlib
import sys
import uuid

# Next, do third-party imports
import globus_sdk
import jinja2


# Get our arguments 
argp = argparse.ArgumentParser()
argp.add_argument('--cutoff-days',
	help='Guest Collections older than this will be emailed',
	type=int,
	default=365 + 14,
)
argp.add_argument('templates',
	help='Path to a directory of Jinja templates',
	type=pathlib.Path,
)
argp.add_argument('outputs',
	help='Path to a directory of emails',
	type=pathlib.Path,
)
argp.add_argument('endpoint',
	help='UUID of the Endpoint to examine',
	type=uuid.UUID,
)
argp.add_argument('collection',
	help='Only send emails for this Mapped Collection',
	type=uuid.UUID,
	nargs='?',
	default=uuid.UUID('00000000-0000-0000-0000-000000000000'),
)
args = argp.parse_args()

# Pull our Client ID from the environment, or use a default one
if 'EEGC_CLIENT_ID' in os.environ:
	GLOBUS_CLIENT_ID = uuid.UUID(os.environ['EEGC_CLIENT_ID'])
else:
	GLOBUS_CLIENT_ID = uuid.UUID('b1aedd57-fb0f-4ba2-9d94-23c832cd41d5')

# Calculate our cutoff date
cutoff_date = datetime.date.today() - datetime.timedelta(days=args.cutoff_days)

# Start by checking the local paths

# Make sure our templates dir is a dir, then set up our Jinja environment
templates_path = args.templates.resolve(strict=True)
if not templates_path.is_dir():
	print(f"{args.templates} does not point to a directory!")
	sys.exit(1)
template_env = jinja2.Environment(
	loader=jinja2.FileSystemLoader(templates_path),
	autoescape=True,
)

# Check for, and load, our Jinja templates
subject_path = templates_path / 'subject.jinja2'
message_path = templates_path / 'message.jinja2'
if not subject_path.is_file():
	print(f"{subject_path} is missing!")
	sys.exit(1)
if not message_path.is_file():
	print(f"{message_path} is missing!")
	sys.exit(1)
subject_template = template_env.get_template('subject.jinja2')
message_template = template_env.get_template('message.jinja2')

# Check our outputs directory exists and is empty
outputs_path = args.outputs.resolve(strict=True)
if not outputs_path.is_dir():
	print(f"{args.outputs} does not point to a directory!")
	sys.exit(1)
if len(list(outputs_path.iterdir())) != 0:
	print(f"{args.outputs} is not an empty directory!")
	sys.exit(1)

# Next, set up our Globus clients, and check our permissions

# Make our Globus App, add Endpoint scopes, and get Auth & Transfer clients
globus = globus_sdk.UserApp('email_expiring_guest_collections',
	client_id=GLOBUS_CLIENT_ID,
)
globus_auth = globus_sdk.AuthClient(app=globus)
globus_transfer = globus_sdk.TransferClient(app=globus)
endpoint_scopes = globus_sdk.GCSClient.get_gcs_endpoint_scopes(args.endpoint)
globus.add_scope_requirements({
	args.endpoint: endpoint_scopes.manage_collections,
})

# Use Transfer to get our Endpoint's Domain.  Also check the optional
# Collection, if provided.
globus_endpoint = globus_transfer.get_endpoint(args.endpoint)
if globus_endpoint['entity_type'] != 'GCSv5_endpoint':
	print(f"UUID {args.endpoint} does not refer to an Endpoint!")
	sys.exit(1)
if args.collection.int != 0:
	globus_collection = globus_transfer.get_endpoint(args.collection)
	if globus_collection['entity_type'] != 'GCSv5_mapped_collection':
		print(f"UUID {args.endpoint} does not refer to a GCS Mapped Collection!")
		sys.exit(1)

# Now time for our Endpoint client, and get our Endpoint's earliest # last-accessed
globus_gcs = globus_sdk.GCSClient(globus_endpoint['gcs_manager_url'],
	app=globus,
)
earliest_last_access=datetime.date.fromisoformat(
	globus_gcs.get_endpoint()['earliest_last_access']
)

# Build our list of Mapped Collections.
# If we were given one, this is simple.  Else query the Endpoint directly.
mapped_collections = dict()
if args.collection.int != 0:
	mapped_collections[args.collection] = globus_gcs.get_collection(args.collection)
else:
	collection_list = globus_gcs.get_collection_list(filter='mapped_collections')
	for collection in collection_list:
		mapped_collections[uuid.UUID(collection['id'])] = collection
print(f"Will examine {len(mapped_collections)} Mapped Collections")

# Build our list of Guest Collections, collecting owner UUIDs as we go
guest_collections = list()
owner_ids: set[uuid.UUID] = set()
for mapped_collection in mapped_collections.values():
	collection_list = globus_gcs.get_collection_list(
		filter=(
			'guest_collections',
			f"last_access <= {cutoff_date}",
		),
		mapped_collection_id=mapped_collection['id'],
	)
	for collection in collection_list:
		guest_collections.append(collection)
		owner_ids.add(collection['identity_id'])
print(f"Will generate emails for {len(guest_collections)} Guest Collections")

# Do we have anything to do?
if len(guest_collections) == 0:
	print('Nothing to do!')
	sys.exit(0)

# Look up our owner Identities, and store their email addresses
owner_emails: dict[uuid.UUID, str] = dict()
for identity in globus_auth.get_identities(ids=owner_ids):
	# Some Identities do not have an email address
	if identity['email'] is not None:
		owner_emails[uuid.UUID(identity['id'])] = identity['email']

# Time to make our emails!
for guest_collection in guest_collections:
	# We'll need various UUIDs
	collection_id = uuid.UUID(guest_collection['id'])
	parent_id = uuid.UUID(guest_collection['mapped_collection_id'])
	owner_id = uuid.UUID(guest_collection['identity_id'])

	# Warn if skip_auto_delete is set on this Guest Collection
	if (
		'skip_auto_delete' in guest_collection
		and guest_collection['skip_auto_delete'] is True
	):
		print(f"Collection has skip_auto_delete: {collection_id} ({guest_collection['display_name']})") 

	# We need contacts to email
	contacts: set[str] = set()

	# Add the Owner's email address, if it has one
	if owner_id in owner_emails:
		contacts.add(owner_emails[owner_id])
	else:
		print(f"Collection owner missing email: {collection_id} ({guest_collection['display_name']})") 

	# If the Collection has a contact email, also add that
	if (
		('contact_email' in guest_collection)
		and (guest_collection['contact_email'] is not None)
		and (len(guest_collection['contact_email']) > 0)
	):
			contacts.add(guest_collection['contact_email'])

	# Prep our paths
	subject_path = outputs_path / f"{collection_id}-subject.txt"
	message_path = outputs_path / f"{collection_id}.message"
	recipients_path = outputs_path / f"{collection_id}-recipients.txt"

	# Prep our template variables
	timedelta_since_last_activity = (
		datetime.date.today()
		- (
			datetime.date.fromisoformat(guest_collection['last_access'])
			if guest_collection['last_access'] is not None
			else earliest_last_access
		  )
		+ datetime.timedelta(days=1)
	)
	template_vars = {
		'collection': guest_collection,
		'parent': mapped_collections[parent_id],
		'earliest_last_access': earliest_last_access,
		'days_since_last_activity': timedelta_since_last_activity.days,
	}
	
	# Process our templates: Make sure subject is one line
	subject_text = subject_template.render(template_vars)
	message_text = message_template.render(template_vars)
	if subject_text.count('\n') > 0:
		print('Subject would be longer than one line!')
		print(subject_text)
		sys.exit(1)

	# Write the files
	with recipients_path.open(mode='w', encoding='ASCII') as recipients_file:
		for contact in contacts:
			recipients_file.write(contact + '\n')
	with subject_path.open(mode='w', encoding='UTF-8') as subject_file:
		subject_file.write(subject_text)
	with message_path.open(mode='w', encoding='UTF-8') as message_file:
		message_file.write(message_text)
