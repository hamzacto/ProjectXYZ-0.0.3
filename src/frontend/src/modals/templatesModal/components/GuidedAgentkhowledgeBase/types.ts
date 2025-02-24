export interface FileItem {
    id: string;
    name: string;
    size: number;
    type: string;
    category: string;
    status: "error" | "completed" | "processing" | "pending";
    progress: number;
    error?: string;
    content: string | ArrayBuffer | null; // Add content property to store the file data
    file_path: string; // Add file_path property
  }
  
  export interface FileCategory {
    id: string;
    name: string;
    files: FileItem[];
  }