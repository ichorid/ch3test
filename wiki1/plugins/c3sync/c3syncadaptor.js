/*\
title: $:/plugins/tiddlywiki/c3sync/c3syncadaptor.js
type: application/javascript
module-type: syncadaptor

A sync adaptor module for synchronising with TiddlyWeb compatible servers

\*/

(function(){

/*jslint node: true, browser: true */
/*global $tw: false */
"use strict";

var CONFIG_HOST_TIDDLER = "$:/config/c3sync/host",
	DEFAULT_HOST_TIDDLER = "$protocol$//$host$/";



function gen64RandInt() {return Math.random().toString(16)}


$tw.hooks.addHook("th-saving-tiddler",function(tiddler) {
	return new $tw.Tiddler(tiddler,{"my-field": gen64RandInt()});
});

function C3SyncAdaptor(options) {
this.wiki = options.wiki;
this.host = this.getHost();
this.hasStatus = false;
this.logger = new $tw.utils.Logger("C3SyncAdaptor");
this.isReadOnly = false;
}

C3SyncAdaptor.prototype.name = "c3sync";

C3SyncAdaptor.prototype.supportsLazyLoading = true;

C3SyncAdaptor.prototype.setLoggerSaveBuffer = function(loggerForSaving) {
	this.logger.setSaveBuffer(loggerForSaving);
};

C3SyncAdaptor.prototype.isReady = function() {
	return this.hasStatus;
};

C3SyncAdaptor.prototype.getHost = function() {
	var text = this.wiki.getTiddlerText(CONFIG_HOST_TIDDLER,DEFAULT_HOST_TIDDLER),
		substitutions = [
			{name: "protocol", value: document.location.protocol},
			{name: "host", value: document.location.host}
		];
	for(var t=0; t<substitutions.length; t++) {
		var s = substitutions[t];
		text = $tw.utils.replaceString(text,new RegExp("\\$" + s.name + "\\$","mg"),s.value);
	}
	return text;
};

C3SyncAdaptor.prototype.getTiddlerInfo = function(tiddler) {
	return {
		id: tiddler.fields.id
	};
};

C3SyncAdaptor.prototype.getTiddlerRevision = function(title) {
	var tiddler = this.wiki.getTiddler(title);
	return tiddler.fields.revision;
};

/*
Get the current status of the TiddlyWeb connection
*/
C3SyncAdaptor.prototype.getStatus = function(callback) {
	// Get status
	var self = this;
	this.logger.log("Getting status");
	$tw.utils.httpRequest({
		url: this.host + "status",
		callback: function(err,data) {
			self.hasStatus = true;
			if(err) {
				return callback(err);
			}
			// Decode the status JSON
			var json = null;
			try {
				json = JSON.parse(data);
			} catch (e) {
			}
			if(json) {
				self.logger.log("Status:",data);
				// Check if we're logged in
				self.isReadOnly = !!json["read_only"];
				self.isAnonymous = !!json.anonymous;
			}
			// Invoke the callback if present
			if(callback) {
				callback(null,self.isLoggedIn,json.username,self.isReadOnly,self.isAnonymous);
			}
		}
	});
};


/*
Retrieve the CSRF token from its cookie
*/
C3SyncAdaptor.prototype.getCsrfToken = function() {
	var regex = /^(?:.*; )?csrf_token=([^(;|$)]*)(?:;|$)/,
		match = regex.exec(document.cookie),
		csrf = null;
	if (match && (match.length === 2)) {
		csrf = match[1];
	}
	return csrf;
};


/*
Save a tiddler and invoke the callback with (err,adaptorInfo,revision)
*/
C3SyncAdaptor.prototype.saveTiddler = function(tiddler,callback) {
	var self = this;
	if(this.isReadOnly) {
		return callback(null);
	}
	$tw.utils.httpRequest({
		url: this.host + "tiddlers/" + encodeURIComponent(tiddler.fields.title),
		type: "PUT",
		headers: {
			"Content-type": "application/json"
		},
		data: this.convertTiddlerToTiddlyWebFormat(tiddler),
		callback: function(err,data,request) {
			if(err) {
				return callback(err);
			}
			// Save the details of the new revision of the tiddler
			var etagInfo = self.parseEtag(request.getResponseHeader("Etag"));
			// Invoke the callback
			// Write {id: <id>} into syncer.tiddlerInfo[title].adaptorInfo
			callback(null,{
				id: etagInfo.id
			}, etagInfo.revision);
		}
	});
};

/*
Load a tiddler and invoke the callback with (err,tiddlerFields)
*/
C3SyncAdaptor.prototype.loadTiddler = function(title,callback) {
	var self = this;
	$tw.utils.httpRequest({
		url: this.host + "tiddlers/" + encodeURIComponent(title),
		callback: function(err,data,request) {
			if(err) {
				return callback(err);
			}
			// Invoke the callback
			callback(null,self.convertTiddlerFromTiddlyWebFormat(JSON.parse(data)));
		}
	});
};

C3SyncAdaptor.prototype.getUpdatedTiddlers = function(title, callback) {
	var self = this;
	$tw.utils.httpRequest({
		url: this.host + "tiddlers.json",
		data: {
			filter: "[all[tiddlers]] -[[$:/isEncrypted]] -[prefix[$:/temp/]] -[prefix[$:/status/]] -[[$:/boot/boot.js]] -[[$:/boot/bootprefix.js]] -[[$:/library/sjcl.js]] -[[$:/core]]"
		},
		callback: function(err,data) {
			// Check for errors
			if(err) {
				return callback(err);
			}
			// Process the tiddlers to make sure the revision is a string
			var tiddlers = JSON.parse(data);
			for(var t=0; t<tiddlers.length; t++) {
				tiddlers[t] = self.convertTiddlerFromTiddlyWebFormat(tiddlers[t]);
			}
			callback(null,tiddlers);
		}
	});
};

/*
Delete a tiddler and invoke the callback with (err)
options include:
tiddlerInfo: the syncer's tiddlerInfo for this tiddler
*/
C3SyncAdaptor.prototype.deleteTiddler = function(title,callback,options) {
	var self = this;
	if(this.isReadOnly) {
		return callback(null);
	}
	// If we don't have an id it means that the tiddler hasn't been seen by the server, so we don't need to delete it
	var id = options.tiddlerInfo.adaptorInfo && options.tiddlerInfo.adaptorInfo.id;
	if(!id) {
		return callback(null);
	}
	// Issue HTTP request to delete the tiddler
	$tw.utils.httpRequest({
		url: this.host + "tiddlers/" + encodeURIComponent(title),
		type: "DELETE",
		callback: function(err,data,request) {
			if(err) {
				return callback(err);
			}
			// Invoke the callback
			callback(null);
		}
	});
};

/*
Convert a tiddler to a field set suitable for PUTting to TiddlyWeb
*/
C3SyncAdaptor.prototype.convertTiddlerToTiddlyWebFormat = function(tiddler) {
	var result = {},
		knownFields = [
			"bag", "created", "creator", "modified", "modifier", "permissions", "recipe", "revision", "tags", "text", "title", "type", "uri"
		];
	if(tiddler) {
		$tw.utils.each(tiddler.fields,function(fieldValue,fieldName) {
			var fieldString = fieldName === "tags" ?
								tiddler.fields.tags :
								tiddler.getFieldString(fieldName); // Tags must be passed as an array, not a string

			if(knownFields.indexOf(fieldName) !== -1) {
				// If it's a known field, just copy it across
				result[fieldName] = fieldString;
			} else {
				// If it's unknown, put it in the "fields" field
				result.fields = result.fields || {};
				result.fields[fieldName] = fieldString;
			}
		});
	}
	// Default the content type
	result.type = result.type || "text/vnd.tiddlywiki";
	return JSON.stringify(result,null,$tw.config.preferences.jsonSpaces);
};

/*
Convert a field set in TiddlyWeb format into ordinary TiddlyWiki5 format
*/
C3SyncAdaptor.prototype.convertTiddlerFromTiddlyWebFormat = function(tiddlerFields) {
	var result = {};
	// Transfer the fields, pulling down the `fields` hashmap
	$tw.utils.each(tiddlerFields,function(element,title,object) {
		if(title === "fields") {
			$tw.utils.each(element,function(element,subTitle,object) {
				result[subTitle] = element;
			});
		} else {
			result[title] = tiddlerFields[title];
		}
	});
	// Make sure the revision is expressed as a string
	if(typeof result.revision === "number") {
		result.revision = result.revision.toString();
	}
	// Some unholy freaking of content types
	if(result.type === "text/javascript") {
		result.type = "application/javascript";
	} else if(!result.type || result.type === "None") {
		result.type = "text/x-tiddlywiki";
	}
	return result;
};

/*
Split a TiddlyWeb Etag into its constituent parts. For example:

```
"system-images_public/unsyncedIcon/946151:9f11c278ccde3a3149f339f4a1db80dd4369fc04"
```

Note that the value includes the opening and closing double quotes.

The parts are:

```
<bag>/<title>/<revision>:<hash>
```
*/
C3SyncAdaptor.prototype.parseEtag = function(etag) {
	var firstSlash = etag.indexOf("/"),
		lastSlash = etag.lastIndexOf("/"),
		colon = etag.lastIndexOf(":");
	if(firstSlash === -1 || lastSlash === -1 || colon === -1) {
		return null;
	} else {
		return {
			id: decodeURIComponent(etag.substring(1,firstSlash)),
			title: decodeURIComponent(etag.substring(firstSlash + 1,lastSlash)),
			revision: etag.substring(lastSlash + 1,colon)
		};
	}
};

if($tw.browser && document.location.protocol.substr(0,4) === "http" ) {
	exports.adaptorClass = C3SyncAdaptor;
}

})();
