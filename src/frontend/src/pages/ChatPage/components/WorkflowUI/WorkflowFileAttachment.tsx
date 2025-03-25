import React from "react";
import { Badge } from "@/components/ui/badge";
import IconComponent from "@/components/common/genericIconComponent";
import { FileAttachment } from "../../types";

interface WorkflowFileAttachmentProps {
  files: Array<FileAttachment | string>;
}

// Determine file icon based on type
const getFileIcon = (type: string): string => {
  if (type.includes('image')) return 'Image';
  if (type.includes('pdf')) return 'FileText';
  if (type.includes('doc')) return 'FileText';
  if (type.includes('sheet') || type.includes('csv') || type.includes('xls')) return 'Table';
  if (type.includes('zip') || type.includes('rar')) return 'Archive';
  if (type.includes('audio') || type.includes('mp3')) return 'Music';
  if (type.includes('video') || type.includes('mp4')) return 'Video';
  return 'File';
};

// Process file to standard format
const processFile = (file: FileAttachment | string): { path: string; name: string; type: string } => {
  if (typeof file === 'string') {
    const name = file.split('/').pop() || file;
    const ext = file.split('.').pop() || 'unknown';
    // Map extension to MIME type
    const typeMap: Record<string, string> = {
      'jpg': 'image/jpeg',
      'jpeg': 'image/jpeg',
      'png': 'image/png',
      'gif': 'image/gif',
      'pdf': 'application/pdf',
      'doc': 'application/msword',
      'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      'xls': 'application/vnd.ms-excel',
      'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      'csv': 'text/csv',
      'txt': 'text/plain',
      'mp3': 'audio/mp3',
      'mp4': 'video/mp4',
      'zip': 'application/zip',
      'rar': 'application/rar',
    };
    return { 
      path: file, 
      name, 
      type: typeMap[ext.toLowerCase()] || 'application/octet-stream'
    };
  }
  return file;
};

export const WorkflowFileAttachment: React.FC<WorkflowFileAttachmentProps> = ({ files }) => {
  if (!files || !Array.isArray(files) || files.length === 0) {
    return null;
  }

  return (
    <div className="mt-3 flex flex-wrap gap-2">
      <span className="text-xs text-muted-foreground w-full mb-1">Attachments:</span>
      {files.map((file, i) => {
        const fileObj = processFile(file);
        const iconName = getFileIcon(fileObj.type);
        
        return (
          <Badge key={i} variant="outline" className="flex items-center gap-1 p-1 pl-2">
            <IconComponent name={iconName} className="h-3 w-3" />
            <a
              href={fileObj.path}
              target="_blank"
              rel="noopener noreferrer"
              className="max-w-[150px] truncate hover:underline"
            >
              {fileObj.name}
            </a>
          </Badge>
        );
      })}
    </div>
  );
}; 