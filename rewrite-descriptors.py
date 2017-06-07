#!/usr/bin/env python3

import glob
import json
import os
import yaml
import sys

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
				elif obj["kind"] == "Service":
					pass
				else:
					raise Exception("Unknown kind {}".format(obj["kind"]))

		print("# merge", len(self.containers), "containers into a single deployment")

		self.basedeployment["spec"]["template"]["spec"]["containers"] = self.containers
		self.basedeployment["metadata"]["name"] = "rewritten-app"

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

		for container in self.containers:
			if "ports" in container:
				for port in container["ports"]:
					if "containerPort" in port:
						portnum = port["containerPort"]
						if portnum in self.ports:
							print("! port conflict", portnum)
						else:
							self.ports.append(portnum)

		print("# rewrite into output.json")
		f = open("output.json", "w")
		json.dump(self.basedeployment, f, indent=2)
		f.close()

dirs = ["."]
if len(sys.argv) > 1:
	dirs = sys.argv[1:]

dr = DescriptorRewriter()
for dirname in dirs:
	dr.scandir(dirname)
dr.parse()
