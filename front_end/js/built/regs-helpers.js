define("regs-helpers",[],function(){return{isIterable:function(e){return typeof e=="array"||typeof e=="object"?!0:!1},fastLink:function(e,t,n){var r=document.createElement("a"),i;return i=$(r),r.href=e,r.innerHTML=t,r.className=n||"",i},idToRef:function(e){var t,n;return n=e.split("-"),isNaN(parseInt(n[0],10))?(t="Supplement ",t+=n[0],n[1]&&(t+=" to Part ",t+=n[1])):n[1]&&(isNaN(parseInt(n[1],10))?(t="Appendix ",t+=n[1],t+=" to Part ",t+=n[0]):(t="§ ",t+=n[0],n.shift(),t+="."+n[0])),t}}});