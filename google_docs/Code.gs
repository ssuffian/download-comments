/**
* @OnlyCurrentDoc
* @NotOnlyCurrentDoc

Requires The following Scopes (via Docs and Drive)
- View and manage documents that this application has been installed in	https://www.googleapis.com/auth/documents.currentonly
- Connect to an external service	https://www.googleapis.com/auth/script.external_request
*/

function exportCommentsAsMarkdown() {
 var doc = DocumentApp.getActiveDocument();
 var fileId = doc.getId();
 
 try {
   // First get document structure from Docs API
   const docContent = Docs.Documents.get(fileId);
   
   // Get comments from Drive API
   var url = `https://www.googleapis.com/drive/v3/files/${fileId}/comments?fields=comments(id,content,author,createdTime,modifiedTime,quotedFileContent,anchor,resolved,replies(id,content,author,createdTime))`;
   
   var response = UrlFetchApp.fetch(url, {
     headers: {
       Authorization: 'Bearer ' + ScriptApp.getOAuthToken()
     },
     muteHttpExceptions: true
   });
   
   var responseData = JSON.parse(response.getContentText());
   let markdown = `# Comments from ${doc.getName()}\n\n`;
   
   // Calculate line numbers from document content
   let lineMap = new Map();
   let currentLine = 1;
   
   if (docContent.body && docContent.body.content) {
     docContent.body.content.forEach((item, index) => {
       if (item.paragraph) {
         lineMap.set(index + 1, currentLine);
         currentLine++;
       }
     });
   }
   
   // Process comments
   responseData.comments
     .map(comment => {
       const lineNumber = comment.anchor ? lineMap.get(parseInt(comment.anchor.segment)) || 1 : 1;
       return {
         ...comment,
         lineNumber
       };
     })
     .sort((a, b) => a.lineNumber - b.lineNumber)
     .forEach(comment => {
       const date = new Date(comment.createdTime).toLocaleString();
       const quotedText = comment.quotedFileContent.value.trim().replace(/[\n\r]/g, ' ');
       const truncatedQuote = quotedText.length > 100 ? quotedText.substring(0, 100) + "..." : quotedText;
       markdown += `* Line ${comment.lineNumber} "${truncatedQuote}"\n`
       markdown += `. * ${comment.author.displayName}, ${date}: ${comment.content}\n`;
       
       if (comment.replies) {
         comment.replies.forEach(reply => {
          if (reply.content && reply.content.trim().length > 0){
           const replyDate = new Date(reply.createdTime).toLocaleString();
           markdown += `  * ${reply.author.displayName}, ${replyDate}: ${reply.content}\n`;
          }
         });
       }

       if (comment.resolved) {
            const resolvedDate = new Date(comment.modifiedTime).toLocaleString();
            markdown += `. * RESOLVED at ${resolvedDate}`
        }
       
       markdown += '\n';
     });
   
   console.log(markdown);
   return markdown;
   
 } catch (error) {
   Logger.log('Error: ' + error.toString());
   throw error;
 }
}
