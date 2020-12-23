/*\
title: $:/plugins/ichorid/tidid/tidid.js
type: application/javascript
module-type: plugin

Unique id generator

\*/

/*!
Shortened version by PMario (1.0 - 2011.05.22) of...
http://www.broofa.com/Tools/Math.uuid.js

Math.uuid.js (v1.4)
http://www.broofa.com
mailto:robert@broofa.com

Copyright (c) 2010 Robert Kieffer
Dual licensed under the MIT and GPL licenses.
*/
(function () {
    /*jslint node: true, browser: true */
    /*global $tw: false */
    "use strict";

// Export name and synchronous status
    exports.name = "savetrail";
    exports.platforms = ["browser"];
    exports.after = ["startup"];
    exports.synchronous = true;

    // Private array of chars to use
    var CHARS = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'.split('');

    Math.uuid = function (len, radix) {
        var chars = CHARS, uuid = new Array(36);
        radix = radix || chars.length;

        if (len) {
            // Compact form
            for (var i = 0; i < len; i++) uuid[i] = chars[0 | Math.random() * radix];
        } else {
            var rnd = 0, r;
            for (var i = 0; i < 36; i++) {
                if (i == 8 || i == 13 || i == 18 || i == 23) {
                    uuid[i] = '-';
                } else if (i == 14) {
                    uuid[i] = '4';
                } else {
                    if (rnd <= 0x02) rnd = 0x2000000 + (Math.random() * 0x1000000) | 0;
                    r = rnd & 0xf;
                    rnd = rnd >> 4;
                    uuid[i] = chars[(i == 19) ? (r & 0x3) | 0x8 : r];
                }
            }
        }

        return uuid.join('');
    };


// Add hooks for trapping user actions
$tw.hooks.addHook("th-saving-tiddler",function(tiddler) {
    var oldTiddler = $tw.wiki.getTiddler(tiddler.fields.title);
    var id = tiddler.fields['id'];
    if (!id) {
        tiddler.fields['id'] = Math.uuid(length || 21, 62);
    }
    return tiddler;
});


})();


