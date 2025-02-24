import DeleteConfirmationModal from "../../../../modals/deleteConfirmationModal";
import GuidedAIAgentTemplatesModal from "@/modals/guidedAIAgentTemplatesModal";

interface ModalsProps {
    openModal: boolean;
    setOpenModal: (value: boolean) => void;
    openDeleteFolderModal: boolean;
    setOpenDeleteFolderModal: (value: boolean) => void;
    handleDeleteFolder: () => void;
}


const GuidedAIAgentModalsComponent = ({
    openModal = false,
    setOpenModal = () => {},
    openDeleteFolderModal = false,
    setOpenDeleteFolderModal = () => {},
    handleDeleteFolder = () => {},
}: ModalsProps) => (
<>
    {openModal && <GuidedAIAgentTemplatesModal open={openModal} setOpen={setOpenModal} />}
    {openDeleteFolderModal && (
    <DeleteConfirmationModal
        open={openDeleteFolderModal}
        setOpen={setOpenDeleteFolderModal}
        onConfirm={() => {
            handleDeleteFolder();
            setOpenDeleteFolderModal(false);
        }}
        description="folder"
        note={
        "Deleting the selected folder will remove all associated flows and components."
        }
    >
        <></>
    </DeleteConfirmationModal>
    )}
</>
);

export default GuidedAIAgentModalsComponent;