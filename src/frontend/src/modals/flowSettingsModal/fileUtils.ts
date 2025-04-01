import axios from "axios";
import { FileCategory, FileItem } from "../templatesModal/components/GuidedAgentkhowledgeBase/types";

const axiosInstance = axios.create({
    baseURL: 'http://localhost:3000/api/v1', 
    headers: {
      'Content-Type': 'application/json',
    },
    timeout: 120000,
});

export async function insertFile(
  file: any, 
  collectionName: string,
  setSuccessData?: (data: { title: string }) => void,
  setErrorData?: (data: { title: string; list: string[] }) => void,
  setNoticeData?: (data: { title: string; link?: string }) => void
) {
    let base64Content: string | undefined;

    if (file.content instanceof ArrayBuffer) {
        base64Content = btoa(
            String.fromCharCode(...Array.from(new Uint8Array(file.content)))
        );
    } else if (
        typeof file.content === 'string' &&
        file.content.startsWith('data:application/pdf;base64,')
    ) {
        base64Content = file.content.split(',')[1];
    } else {
        console.error('Invalid file content format for', file.name);
        return;
    }

    if (!base64Content) {
        console.error('No content found for', file.name);
        return;
    }
    function isValidBase64(base64String: string): boolean {
        const base64Regex = /^[A-Za-z0-9+/]+={0,2}$/;
        return base64String.length % 4 === 0 && base64Regex.test(base64String);
    }
    if (!isValidBase64(base64Content)) {
        console.error('Invalid Base64 content detected for', file.name);
        return;
    }

    const payload = {
        id: file.id,
        name: file.name,
        size: file.size,
        type: file.type,
        category: file.category,
        content: base64Content,
        file_path: file.file_path,
        collection_name: collectionName,
        batch_size: 50,
        chunk_size: 512,
        chunk_overlap: 200,
    };

    try {
        const { data } = await axiosInstance.post('/milvus/insert_file', payload);
        const taskId = data.task_id;
        console.log(`Task ${taskId} started for file ${file.name}`);

        // Poll for status updates
        const pollStatus = async () => {
            try {
                const { data: status } = await axiosInstance.get(`/milvus/task/${taskId}`);
                // Update UI progress if available
                if (status.total_chunks > 0) {
                    const progress = (status.processed_chunks / status.total_chunks) * 100;
                    updateFileProgress(file.id, progress);
                    if (setNoticeData) {
                        setNoticeData({
                            title: `Processing ${file.name} ${Math.round(progress)}%`});
                    }
                }
                if (status.status === 'completed') {
                    console.log(`File ${file.name} processing completed`);
                    updateFileStatus(file.id, 'completed');
                    if (setSuccessData) {
                        setSuccessData({
                            title: `${file.name} processed successfully`,
                        });
                    }
                    return;
                } else if (status.status === 'failed') {
                    console.error(`File ${file.name} processing failed:`, status.error);
                    updateFileStatus(file.id, 'failed', status.error);
                    if (setErrorData) {
                        setErrorData({
                            title: `Error processing ${file.name}`,
                            list: [status.error || 'Unknown error occurred']
                        });
                    }
                    return;
                }
                // Poll again after a delay
                setTimeout(pollStatus, 1000);
            } catch (error: any) {
                console.error(`Error checking status for ${file.name}:`, error);
                updateFileStatus(file.id, 'failed', error.message);
                if (setErrorData) {
                    setErrorData({
                        title: `Error processing ${file.name}`,
                        list: [error.message]
                    });
                }
            }
        };
        pollStatus();
    } catch (error: any) {
        console.error(`Error inserting file ${file.name}:`, error);
        if (setErrorData) {
            setErrorData({
                title: `Error uploading ${file.name}`,
                list: [error.message]
            });
        }
    }
}

// Helper functions for UI updates
function updateFileProgress(fileId: string, progress: number) {
    const progressElement = document.querySelector(`[data-file-id="${fileId}"] .progress`) as HTMLElement;
    if (progressElement) {
        progressElement.style.width = `${progress}%`;
    }
}

function updateFileStatus(fileId: string, status: 'completed' | 'failed', error?: string) {
    const statusElement = document.querySelector(`[data-file-id="${fileId}"] .status`);
    if (statusElement) {
        statusElement.textContent = status;
        if (error) {
            statusElement.setAttribute('title', error);
        }
    }
}

export const insertFilesIntoDatabase = async (
  categories: FileCategory[],
  collectionName: string,
  setNoticeData?: (data: { title: string; link?: string }) => void,
  setErrorData?: (data: { title: string; list: string[] }) => void,
  setSuccessData?: (data: { title: string }) => void
) => {
  try {
    if (setNoticeData) {
      setNoticeData({
        title: "Your files are being processed in the background. You can continue using your AI Agent, but please note that responses may not include information from files still being processed. Check back in a few minutes for optimal results.",
        link: "Processing..."
      });
    }
    
    const files: FileItem[] = [];
    categories.forEach((cat) => {
        files.push(...cat.files);
    });
    // Process files with a concurrency limit of 4 (adjust as needed)
    await processInBatches(files, (file) => insertFile(file, collectionName, setSuccessData, setErrorData, setNoticeData), 4);
  } catch (error) {
    if (setErrorData) {
      setErrorData({
        title: "Error uploading files",
        list: [(error as Error).message]
      });
    }
    throw error;
  }
};

// A simple concurrency limiter
export async function processInBatches<T>(items: T[], handler: (item: T) => Promise<void>, concurrency: number = 4) {
    const executing: Promise<void>[] = [];
    const settled = new Map<Promise<void>, boolean>();

    for (const item of items) {
        const p = handler(item).then(() => {
            settled.set(p, true);
        });
        executing.push(p);
        if (executing.length >= concurrency) {
            await Promise.race(executing);
            // Remove resolved promises
            executing.splice(0, executing.length, ...executing.filter(p => !settled.get(p)));
        }
    }
    await Promise.all(executing);
}

export const deleteFileFromDatabase = async (
  fileId: string,
  collectionName: string,
  setErrorData?: (data: { title: string; list: string[] }) => void
) => {
  try {
    // Call the backend API to delete the file from Milvus
    const { data } = await axiosInstance.delete(`/milvus/files/${collectionName}/${fileId}`);
    console.log(`File ${fileId} deleted from collection ${collectionName}:`, data);
    return true;
  } catch (error) {
    if (setErrorData) {
      setErrorData({
        title: "Error deleting file",
        list: [(error as Error).message]
      });
    }
    console.error(`Error deleting file ${fileId} from collection ${collectionName}:`, error);
    return false;
  }
};

