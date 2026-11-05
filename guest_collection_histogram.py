#!python3
# vim: ts=4 sw=4 noet

# A script to make a histogram of how long it has been (in months) since
# Guest Collections were last accessed.
# A. Karl Kornel, akkornel@stanford.edu, 2026-11
# © 2026 The Board of Trustees of the Leland Stanford Junior University
# Much of the script was created using Anthropic Opus 5.5 Medium & Claude
# Cowork.

# An example of how to run the script:
# uv run guest_collection_histogram.py ENDPOINT_UUID [COLLECTION_UUID] > ages.csv

# By default, the script will run on all Mapped Collections of an Endpoint.  To
# only run on one Mapped Collection, provide that Collection's UUID.  You must
# have at least the Activity Manager Role, either on the specific Collection,
# or on the entire Endpoint.

# The CSV is written to standard output, with two columns:
# * "Months Since Last Access": The number of whole months since the Guest
#   Collection was last accessed.
# * "Number of Guest Collections": How many Guest Collections fall into that
#   bucket.
# Every month count from 0 through the least-recently-accessed Guest Collection
# gets a row, even if no Guest Collections fall into that bucket.
# Status messages are written to standard error, so they won't end up in your
# CSV.

# Months are calculated from the Guest Collection's `last_access` field.  If a
# Guest Collection has never been accessed (`last_access` is None), the
# Endpoint's `earliest_last_access` date is used instead.  For Collection
# document schemas, see
# https://docs.globus.org/globus-connect-server/v5.4/api/openapi_schemas/:

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
# ]
# ///

# Start with stdlib packages
import argparse
import collections
import csv
import datetime
import os
import sys
import uuid

# Next, do third-party imports
import globus_sdk


# A helper to print status messages to stderr, keeping stdout for the CSV
def status(message: str) -> None:
	print(message, file=sys.stderr)


# Calculate the number of whole months between two dates
def months_between(start: datetime.date, end: datetime.date) -> int:
	months = (end.year - start.year) * 12 + (end.month - start.month)
	# If we haven't reached the day-of-month yet, the last month isn't whole
	if end.day < start.day:
		months -= 1
	return max(months, 0)


# Get our arguments
argp = argparse.ArgumentParser()
argp.add_argument('endpoint',
	help='UUID of the Endpoint to examine',
	type=uuid.UUID,
)
argp.add_argument('collection',
	help='Only examine Guest Collections of this Mapped Collection',
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

# Set up our Globus clients, and check our permissions

# Make our Globus App, add Endpoint scopes, and get a Transfer client
globus = globus_sdk.UserApp('guest_collection_histogram',
	client_id=GLOBUS_CLIENT_ID,
)
globus_transfer = globus_sdk.TransferClient(app=globus)
endpoint_scopes = globus_sdk.GCSClient.get_gcs_endpoint_scopes(args.endpoint)
globus.add_scope_requirements({
	args.endpoint: endpoint_scopes.manage_collections,
})

# Use Transfer to get our Endpoint's Domain.  Also check the optional
# Collection, if provided.
globus_endpoint = globus_transfer.get_endpoint(args.endpoint)
if globus_endpoint['entity_type'] != 'GCSv5_endpoint':
	status(f"UUID {args.endpoint} does not refer to an Endpoint!")
	sys.exit(1)
if args.collection.int != 0:
	globus_collection = globus_transfer.get_endpoint(args.collection)
	if globus_collection['entity_type'] != 'GCSv5_mapped_collection':
		status(f"UUID {args.collection} does not refer to a GCS Mapped Collection!")
		sys.exit(1)
	if uuid.UUID(globus_collection['non_functional_endpoint_id']) != args.endpoint:
		status(f"Collection {args.collection} is not on Endpoint {args.endpoint}!")
		sys.exit(1)

# Now time for our Endpoint client, and get our Endpoint's earliest last-accessed
globus_gcs = globus_sdk.GCSClient(globus_endpoint['gcs_manager_url'],
	app=globus,
)
earliest_last_access = datetime.date.fromisoformat(
	globus_gcs.get_endpoint()['earliest_last_access']
)

# Build our list of Mapped Collection UUIDs.
# If we were given one, this is simple.  Else query the Endpoint directly.
mapped_collection_ids: list[uuid.UUID] = list()
if args.collection.int != 0:
	mapped_collection_ids.append(args.collection)
else:
	collection_list = globus_gcs.paginated.get_collection_list(
		filter='mapped_collections',
	).items()
	for collection in collection_list:
		mapped_collection_ids.append(uuid.UUID(collection['id']))
status(f"Will examine {len(mapped_collection_ids)} Mapped Collections")

# Go through each Mapped Collection's Guest Collections, counting months since
# last access
today = datetime.date.today()
age_counts: collections.Counter[int] = collections.Counter()
guest_collection_count = 0
for mapped_collection_id in mapped_collection_ids:
	collection_list = globus_gcs.paginated.get_collection_list(
		filter='guest_collections',
		mapped_collection_id=mapped_collection_id,
	).items()
	for collection in collection_list:
		# If never accessed, fall back to when the Endpoint started tracking
		last_access = (
			datetime.date.fromisoformat(collection['last_access'])
			if collection['last_access'] is not None
			else earliest_last_access
		)
		age_counts[months_between(last_access, today)] += 1
		guest_collection_count += 1
status(f"Found {guest_collection_count} Guest Collections")

# Write out our CSV.  Include every month count from zero through the highest.
csv_writer = csv.writer(sys.stdout)
csv_writer.writerow(('Months Since Last Access', 'Number of Guest Collections'))
if len(age_counts) > 0:
	for age in range(0, max(age_counts) + 1):
		csv_writer.writerow((age, age_counts[age]))
