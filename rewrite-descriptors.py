#!/usr/bin/env python3

import glob
import json
import os
import yaml
import sys
import shutil

def has_keychain(d, keychain):
	if keychain[0] in d:
		if len(keychain) == 1:
			return True
		return has_keychain(d[keychain[0]], keychain[1:])
	return False

class DescriptorRewriter:
	def __init__(self):
		self.files = []
		self.objects = []
		self.label = None
		self.containers = []
		self.basedeployment = None
		self.ports = []
		self.originfiles = {}

	def scandir(self, rootdir):
		if rootdir.endswith(".yaml"):
			self.files.append(rootdir)
		elif rootdir.endswith(".json"):
			self.files.append(rootdir)
		for root, dirs, files in os.walk(rootdir):
			for filename in files:
				if filename == "output.json":
					continue
				path = os.path.join(root, filename)
				#print(path)
				if filename.endswith(".yaml"):
					self.files.append(path)
				elif filename.endswith(".json"):
					self.files.append(path)

	def parse(self):
		for filename in self.files:
			#print("/p", filename)
			if filename.endswith(".yaml"):
				self.objects.append(yaml.load(open(filename)))
			elif filename.endswith(".json"):
				self.objects.append(json.load(open(filename)))
			self.objects[-1]["*origin*"] = filename

		#print(self.objects)
		for obj in self.objects:
			if "kind" in obj:
				if obj["kind"] == "Namespace":
					ns = obj["metadata"]["name"]
					print("# convert namespace {} to label".format(ns))
					self.label = ns
				elif obj["kind"] == "Deployment":
					if not self.basedeployment:
						self.basedeployment = obj
					if has_keychain(obj, ["metadata", "namespace"]):
						ns = obj["metadata"]["namespace"]
						print("# convert namespace {} to label".format(ns))
						obj["spec"]["template"]["metadata"]["labels"]["namespaceLabel"] = ns
						del obj["metadata"]["namespace"]
					if has_keychain(obj, ["spec", "template", "spec", "containers"]):
						containers = obj["spec"]["template"]["spec"]["containers"]
						self.containers += containers
						for container in containers:
							self.originfiles[container["name"]] = obj["*origin*"]
				elif obj["kind"] == "Service":
					pass
				else:
					raise Exception("Unknown kind {}".format(obj["kind"]))

		for container in self.containers:
			r = container.setdefault("resources", {})
			l = container["resources"].setdefault("limits", {})
			c = container["resources"]["limits"].setdefault("cpu", "500m")
			if c[-1] == "m":
				c = int(c[:-1])
			else:
				c = int(float(c) * 100)
			c //= 5
			print("# constrain to", c, "millicores")
			container["resources"]["limits"]["cpu"] = "{}m".format(c)

		exclusions = []
		joinedcontainers = []
		for container in self.containers:
			if "ports" in container:
				for port in container["ports"]:
					if "containerPort" in port:
						portnum = port["containerPort"]
						if portnum in self.ports:
							exclusion = self.originfiles[container["name"]]
							exclusions.append(exclusion)
							print("! port conflict", portnum, "excluding", exclusion)
						else:
							self.ports.append(portnum)
							joinedcontainers.append(container)

		print("# merge", len(joinedcontainers), "out of", len(joinedcontainers) + len(exclusions), "containers into a single deployment")

		self.basedeployment["spec"]["template"]["spec"]["containers"] = joinedcontainers
		self.basedeployment["metadata"]["name"] = "rewritten-app"
		del self.basedeployment["*origin*"]

		os.makedirs("output", exist_ok=True)

		print("# rewrite into output.json")
		f = open("output/output.json", "w")
		json.dump(self.basedeployment, f, indent=2, sort_keys=True)
		f.close()

		for exclusion in exclusions:
			shutil.copy(exclusion, "output")

dirs = ["."]
if len(sys.argv) > 1:
	dirs = sys.argv[1:]

dr = DescriptorRewriter()
for dirname in dirs:
	dr.scandir(dirname)
dr.parse()
